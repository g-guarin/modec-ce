"""
Modelo fuera de línea del caché de prefijos de DeepSeek (Context Caching on Disk).

Implementa solo las reglas que la documentación oficial declara
(https://api-docs.deepseek.com/guides/kv_cache/, leída el 2026-11-20):

  R1  Una petición acierta en caché solo si su entrada coincide COMPLETAMENTE con una
      "unidad de prefijo" ya almacenada (cuenta el tramo más largo que coincide).
  R2  Se crean unidades al final de la entrada de cada petición.
  R3  Se crean unidades al detectar un prefijo común entre peticiones; por eso
      A+B, luego A+C no acierta, y A+D (tercera) sí acierta sobre A.
  R4  También se crean unidades "a intervalos fijos de tokens" en entradas largas.
      El intervalo NO se publica: aquí es un parámetro desactivado por defecto.

Lo que la documentación NO declara y por tanto NO se asume: tamaño mínimo de unidad,
tamaño de bloque (p. ej. 64 tokens), ventana del Sliding Window Attention y duración.
El caché es de "mejor esfuerzo": el resultado es una COTA SUPERIOR bajo las reglas
documentadas para peticiones secuenciales, no una predicción de factura.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence

from .tokens import tokenizar

REGLAS_ID = "DEEPSEEK-KVCACHE-DOC-2026-11-20:R1-R3(+R4 opcional)"


def _hash_prefijos(tokens: Sequence[str]) -> list[bytes]:
    """h[i] = huella del prefijo de longitud i+1 (encadenada, O(n))."""
    salida: list[bytes] = []
    acc = b""
    for t in tokens:
        acc = hashlib.blake2b(acc + b"\x1f" + t.encode("utf-8"), digest_size=16).digest()
        salida.append(acc)
    return salida


def _prefijo_comun(a: Sequence[bytes], b: Sequence[bytes]) -> int:
    """Longitud del prefijo común usando las huellas encadenadas (búsqueda binaria)."""
    lo, hi = 0, min(len(a), len(b))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if a[mid - 1] == b[mid - 1]:
            lo = mid
        else:
            hi = mid - 1
    return lo


@dataclass
class ResultadoPeticion:
    tokens_entrada: int
    tokens_acierto: int

    @property
    def tokens_fallo(self) -> int:
        return self.tokens_entrada - self.tokens_acierto


@dataclass
class ModeloCachePrefijos:
    intervalo_fijo: int | None = None          # R4: no documentado; None = no se aplica
    min_unidad: int = 1                         # no documentado; 1 = sin mínimo
    _unidades: dict[int, set[bytes]] = field(default_factory=dict)
    _anteriores: list[list[bytes]] = field(default_factory=list)

    def _guardar(self, longitud: int, huella: bytes) -> None:
        if longitud >= self.min_unidad:
            self._unidades.setdefault(longitud, set()).add(huella)

    def procesar(self, texto: str) -> ResultadoPeticion:
        h = _hash_prefijos(tokenizar(texto))
        n = len(h)
        acierto = 0
        for longitud in sorted(self._unidades, reverse=True):      # R1: la unidad más larga que coincide entera
            if longitud <= n and h[longitud - 1] in self._unidades[longitud]:
                acierto = longitud
                break
        # Después de servir la petición se crean las nuevas unidades.
        if n:
            self._guardar(n, h[n - 1])                              # R2
        for previa in self._anteriores:                             # R3
            comun = _prefijo_comun(h, previa)
            if comun:
                self._guardar(comun, h[comun - 1])
        if self.intervalo_fijo:                                     # R4 (opcional)
            for k in range(self.intervalo_fijo, n + 1, self.intervalo_fijo):
                self._guardar(k, h[k - 1])
        self._anteriores.append(h)
        return ResultadoPeticion(n, acierto)


def simular(textos: Sequence[str], **kwargs) -> list[ResultadoPeticion]:
    modelo = ModeloCachePrefijos(**kwargs)
    return [modelo.procesar(t) for t in textos]
