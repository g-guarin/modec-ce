"""
Proveedor local para el piloto: servidor HTTP compatible con el API de chat de DeepSeek,
respaldado por un transformador real (PyTorch, CPU) con caché de prefijos KV.

Para qué sirve:
  * Ejecutar el piloto completo (HTTP, JSON, `usage`, evidencia sellada) sin clave ni costo.
  * Medir el efecto de rendimiento del mecanismo: con caché, el prefijo ya calculado no se
    vuelve a procesar. La latencia medida es real en este equipo.

Límites declarados:
  * Pesos aleatorios con semilla fija: el texto generado no tiene significado. Se mide el
    cómputo, no la calidad. No se descarga ningún modelo.
  * El caché sigue las reglas documentadas de DeepSeek (R1–R3, ver cache.py), con un número
    acotado de unidades en memoria (LRU). No reproduce la infraestructura del proveedor.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import torch
import torch.nn.functional as F

from .tokens import tokenizar

VOCAB = 4096


@dataclass(frozen=True)
class ConfigMini:
    capas: int = 4
    dim: int = 256
    cabezas: int = 4
    max_pos: int = 16384
    semilla: int = 2026


class MiniTransformer(torch.nn.Module):
    """Decodificador causal mínimo con caché KV explícito (lista de (K, V) por capa)."""

    def __init__(self, cfg: ConfigMini = ConfigMini()):
        super().__init__()
        torch.manual_seed(cfg.semilla)
        self.cfg = cfg
        self.emb = torch.nn.Embedding(VOCAB, cfg.dim)
        self.pos = torch.nn.Embedding(cfg.max_pos, cfg.dim)
        self.qkv = torch.nn.ModuleList(torch.nn.Linear(cfg.dim, 3 * cfg.dim) for _ in range(cfg.capas))
        self.proy = torch.nn.ModuleList(torch.nn.Linear(cfg.dim, cfg.dim) for _ in range(cfg.capas))
        self.mlp = torch.nn.ModuleList(torch.nn.Sequential(
            torch.nn.Linear(cfg.dim, 4 * cfg.dim), torch.nn.GELU(), torch.nn.Linear(4 * cfg.dim, cfg.dim))
            for _ in range(cfg.capas))
        self.norm1 = torch.nn.ModuleList(torch.nn.LayerNorm(cfg.dim) for _ in range(cfg.capas))
        self.norm2 = torch.nn.ModuleList(torch.nn.LayerNorm(cfg.dim) for _ in range(cfg.capas))
        self.salida = torch.nn.Linear(cfg.dim, VOCAB)
        self.eval()

    @torch.inference_mode()
    def avanzar(self, ids: list[int], pasado: list[tuple[torch.Tensor, torch.Tensor]] | None):
        """Procesa `ids` nuevos sobre el caché `pasado`. Devuelve logits del último token y caché ampliado."""
        cfg = self.cfg
        L = pasado[0][0].shape[1] if pasado else 0
        n = len(ids)
        if L + n > cfg.max_pos:
            raise ValueError("entrada más larga que max_pos")
        x = self.emb(torch.tensor(ids)) + self.pos(torch.arange(L, L + n))
        h, dh = cfg.cabezas, cfg.dim // cfg.cabezas
        nuevo = []
        mascara = torch.ones(n, L + n, dtype=torch.bool).tril(diagonal=L)
        for i in range(cfg.capas):
            q, k, v = self.qkv[i](self.norm1[i](x)).split(cfg.dim, dim=-1)
            q, k, v = (t.view(n, h, dh).transpose(0, 1) for t in (q, k, v))
            if pasado:
                k = torch.cat([pasado[i][0], k], dim=1)
                v = torch.cat([pasado[i][1], v], dim=1)
            nuevo.append((k, v))
            a = F.scaled_dot_product_attention(q, k, v, attn_mask=mascara)
            x = x + self.proy[i](a.transpose(0, 1).reshape(n, cfg.dim))
            x = x + self.mlp[i](self.norm2[i](x))
        return self.salida(x[-1]), nuevo


def ids_de(texto: str) -> list[int]:
    return [int.from_bytes(hashlib.blake2b(t.encode("utf-8"), digest_size=4).digest(), "big") % VOCAB
            for t in tokenizar(texto)]


def _recortar(kv, longitud: int):
    return [(k[:, :longitud].clone(), v[:, :longitud].clone()) for k, v in kv]


class CachePrefijosKV:
    """Unidades de prefijo con su caché KV real, según R1–R3 de la documentación de DeepSeek."""

    def __init__(self, max_unidades: int = 12):
        self.max_unidades = max_unidades
        self.unidades: OrderedDict[tuple[int, ...], list] = OrderedDict()
        self.anteriores: list[tuple[tuple[int, ...], list]] = []

    def buscar(self, ids: tuple[int, ...]):
        mejor = None
        for pref, kv in self.unidades.items():                       # R1
            if len(pref) <= len(ids) and ids[: len(pref)] == pref and (mejor is None or len(pref) > len(mejor[0])):
                mejor = (pref, kv)
        if mejor:
            self.unidades.move_to_end(mejor[0])
        return mejor

    def _guardar(self, pref: tuple[int, ...], kv) -> None:
        if not pref:
            return
        self.unidades[pref] = kv
        self.unidades.move_to_end(pref)
        while len(self.unidades) > self.max_unidades:
            self.unidades.popitem(last=False)

    def registrar(self, ids: tuple[int, ...], kv) -> None:
        self._guardar(ids, kv)                                        # R2
        for previo, _kv_previo in self.anteriores[-self.max_unidades:]:  # R3
            n = 0
            # strict=False a propósito: se compara el prefijo común y se detiene en el más corto.
            for a, b in zip(ids, previo, strict=False):
                if a != b:
                    break
                n += 1
            if 0 < n < len(ids):
                self._guardar(ids[:n], _recortar(kv, n))
        self.anteriores.append((ids, kv))
        self.anteriores = self.anteriores[-self.max_unidades:]


class ServicioLocal:
    def __init__(self, cfg: ConfigMini = ConfigMini(), max_unidades: int = 12, tokens_salida_max: int = 8):
        torch.set_num_threads(max(1, torch.get_num_threads()))
        self.modelo = MiniTransformer(cfg)
        self.cache = CachePrefijosKV(max_unidades)
        self.tokens_salida_max = tokens_salida_max
        self._lock = threading.Lock()

    def completar(self, texto: str, max_tokens: int) -> dict[str, Any]:
        with self._lock:
            ids = tuple(ids_de(texto))
            t0 = time.perf_counter()
            hallado = self.cache.buscar(ids)
            acierto = len(hallado[0]) if hallado else 0
            pasado = hallado[1] if hallado else None
            logits, kv = self.modelo.avanzar(list(ids[acierto:]), pasado)
            t_prefill = time.perf_counter() - t0
            self.cache.registrar(ids, kv)
            generados = []
            for _ in range(min(max_tokens, self.tokens_salida_max)):
                siguiente = int(torch.argmax(logits))
                generados.append(siguiente)
                logits, kv = self.modelo.avanzar([siguiente], kv)
            return {
                "id": "local-" + hashlib.sha256(bytes(str(ids), "utf-8")).hexdigest()[:12],
                "object": "chat.completion",
                "model": "mini-transformer-local",
                "choices": [{"index": 0, "message": {"role": "assistant",
                                                     "content": " ".join(f"t{g}" for g in generados)},
                             "finish_reason": "length"}],
                "usage": {"prompt_tokens": len(ids), "completion_tokens": len(generados),
                          "prompt_cache_hit_tokens": acierto, "prompt_cache_miss_tokens": len(ids) - acierto,
                          "prefill_ms": round(t_prefill * 1000, 1)},
            }


def crear_servidor(servicio: ServicioLocal, puerto: int = 0) -> ThreadingHTTPServer:
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silencioso
            return

        def do_POST(self):
            if self.path != "/chat/completions":
                self.send_error(404)
                return
            largo = int(self.headers.get("Content-Length", "0"))
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            texto = "".join(m.get("content", "") for m in datos.get("messages", []))
            cuerpo = json.dumps(servicio.completar(texto, int(datos.get("max_tokens", 8)))).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
