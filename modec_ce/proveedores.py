"""
Adaptadores de proveedor para el piloto A/B.

Cada adaptador sabe construir la petición HTTP y normalizar el `usage` del proveedor a
cuatro magnitudes: acierto de caché, escritura de caché, entrada sin caché y salida.
La presencia de cada campo se clasifica con PESD P2: un campo AUSENTE no es cero y deja
la llamada NO_EVALUABLE.

Política de caché, igual para todos los brazos de un mismo proveedor (lo único que
cambia entre brazos es el orden de los segmentos):
  deepseek    automática (Context Caching on Disk)
  openai      automática (prefijo ≥ 1 024 tokens)
  openrouter  la del proveedor subyacente; uso en prompt_tokens_details
  anthropic   explícita: cache_control tras el 2.º y el 3.er segmento de contenido de cada
              petición (el segmento 0 es la cabecera de la corrida)
  local       servidor de este equipo con un transformador real y caché de prefijos
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .evidencia import Registro, registro

SISTEMA = "Responde en español, de forma breve."


@dataclass(frozen=True)
class UsoNormalizado:
    acierto: int
    escritura: int
    fallo: int
    salida: int
    presencia: dict[str, str]
    evaluable: bool
    costo_plataforma: str | None = None     # si el proveedor informa el costo (OpenRouter)


def _presencia(usage: Mapping[str, Any] | None, rutas: Sequence[str]) -> dict[str, str]:
    datos = dict(usage or {})
    return {r: registro(datos, r).name for r in rutas}


def _entero(usage: Mapping[str, Any], ruta: str) -> int | None:
    actual: Any = usage
    for p in ruta.split("."):
        if not isinstance(actual, Mapping) or p not in actual:
            return None
        actual = actual[p]
    if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
        return None
    return actual


def _no_evaluable(presencia: dict[str, str]) -> UsoNormalizado:
    return UsoNormalizado(0, 0, 0, 0, presencia, False)


@dataclass(frozen=True)
class Proveedor:
    nombre: str
    url: str
    variable_clave: str
    modelo_por_defecto: str
    cabeceras: Callable[[str], dict[str, str]]
    cuerpo: Callable[[str, Sequence[str], int, Mapping[str, Any]], dict[str, Any]]
    normalizar: Callable[[Mapping[str, Any] | None], UsoNormalizado]
    opciones_por_defecto: Mapping[str, Any]
    texto_respuesta: Callable[[Mapping[str, Any]], str]


# ------------------------------------------------------------------ estilo OpenAI

def _cuerpo_chat(modelo: str, segmentos: Sequence[str], max_salida: int, opciones: Mapping[str, Any]) -> dict:
    clave_max = opciones.get("_clave_max_tokens", "max_tokens")
    extra = {k: v for k, v in opciones.items() if not k.startswith("_")}
    return {"model": modelo, "stream": False, clave_max: max_salida,
            "messages": [{"role": "system", "content": SISTEMA},
                         {"role": "user", "content": "\n\n".join(segmentos)}], **extra}


def _texto_chat(datos: Mapping[str, Any]) -> str:
    return (((datos.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""


def _norm_deepseek(usage):
    rutas = ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    pres = _presencia(usage, rutas)
    if any(v != Registro.PRESENTE.name for v in pres.values()):
        return _no_evaluable(pres)
    vals = {r: _entero(usage, r) for r in rutas}
    if None in vals.values():
        return _no_evaluable(pres)
    return UsoNormalizado(vals["prompt_cache_hit_tokens"], 0, vals["prompt_cache_miss_tokens"],
                          vals["completion_tokens"], pres, True)


def _norm_openai(usage):
    rutas = ("prompt_tokens", "completion_tokens", "prompt_tokens_details.cached_tokens")
    pres = _presencia(usage, rutas)
    if any(v != Registro.PRESENTE.name for v in pres.values()):
        return _no_evaluable(pres)
    p, c, h = (_entero(usage, r) for r in rutas)
    if None in (p, c, h) or h > p:
        return _no_evaluable(pres)
    escritura = _entero(usage, "prompt_tokens_details.cache_write_tokens") or 0
    return UsoNormalizado(h, escritura, max(0, p - h - escritura), c, pres, True)


def _norm_openrouter(usage):
    u = _norm_openai(usage)
    costo = (usage or {}).get("cost")
    if u.evaluable and isinstance(costo, (int, float)) and not isinstance(costo, bool):
        return UsoNormalizado(u.acierto, u.escritura, u.fallo, u.salida, u.presencia, True, f"{costo:.9f}")
    return u


# ------------------------------------------------------------------ Anthropic

def _cuerpo_anthropic(modelo, segmentos, max_salida, opciones):
    bloques = []
    for i, s in enumerate(segmentos):
        b: dict[str, Any] = {"type": "text", "text": s}
        if i in (2, 3):                      # tras el 2.º y 3.er segmento de contenido, igual en todos los brazos
            b["cache_control"] = {"type": "ephemeral"}
        bloques.append(b)
    return {"model": modelo, "max_tokens": max_salida, "system": SISTEMA,
            "messages": [{"role": "user", "content": bloques}], **{k: v for k, v in opciones.items()}}


def _norm_anthropic(usage):
    rutas = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    pres = _presencia(usage, rutas)
    if any(v != Registro.PRESENTE.name for v in pres.values()):
        return _no_evaluable(pres)
    i, o, r, w = (_entero(usage, x) for x in rutas)
    if None in (i, o, r, w):
        return _no_evaluable(pres)
    return UsoNormalizado(r, w, i, o, pres, True)


def _texto_anthropic(datos):
    return "".join(b.get("text", "") for b in datos.get("content") or [] if isinstance(b, Mapping))


# ------------------------------------------------------------------ registro

PROVEEDORES: dict[str, Proveedor] = {
    "deepseek": Proveedor(
        "deepseek", "https://api.deepseek.com/chat/completions", "DEEPSEEK_API_KEY", "deepseek-flash",
        lambda k: {"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        _cuerpo_chat, _norm_deepseek, {"thinking": {"type": "disabled"}}, _texto_chat),
    "openai": Proveedor(
        "openai", "https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY", "gpt-4.1-mini",
        lambda k: {"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        _cuerpo_chat, _norm_openai, {}, _texto_chat),
    "openrouter": Proveedor(
        "openrouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "deepseek/deepseek-chat",
        lambda k: {"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        _cuerpo_chat, _norm_openrouter, {"usage": {"include": True}}, _texto_chat),
    "anthropic": Proveedor(
        "anthropic", "https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY", "claude-haiku-5-5",
        lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        _cuerpo_anthropic, _norm_anthropic, {}, _texto_anthropic),
    "local": Proveedor(
        "local", "http://127.0.0.1:{puerto}/chat/completions", "MODEC_CE_LOCAL_KEY", "mini-transformer-local",
        lambda k: {"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        _cuerpo_chat, _norm_deepseek, {}, _texto_chat),
}


def url_de(proveedor: Proveedor, puerto_local: int | None = None) -> str:
    if proveedor.nombre == "local":
        if not puerto_local:
            raise ValueError("el proveedor local necesita puerto")
        return proveedor.url.format(puerto=int(puerto_local))
    return proveedor.url


def clave_de(proveedor: Proveedor) -> str:
    if proveedor.nombre == "local":
        return os.environ.get(proveedor.variable_clave, "sin-clave-local")
    return os.environ.get(proveedor.variable_clave, "")


def a_json(cuerpo: Mapping[str, Any]) -> bytes:
    return json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
