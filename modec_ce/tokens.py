"""
Tokenización aproximada para el modelo fuera de línea.

El tokenizador oficial de DeepSeek no está disponible sin red. Para la simulación se
usa una segmentación determinista (palabras y signos). Los conteos son ESTIMADOS:
sirven para comparar disposiciones del mismo contenido entre sí, no para predecir
facturas. La medición real la entrega el proveedor en `usage`.
"""
from __future__ import annotations

import re

TOKENIZADOR_ID = "aprox-regex-v1"
PROCEDENCIA = "ESTIMADO"

_PATRON = re.compile(r"\w{1,6}|[^\w\s]", re.UNICODE)


def tokenizar(texto: str) -> list[str]:
    """Segmenta en piezas de hasta 6 caracteres de palabra o un signo."""
    return _PATRON.findall(texto)


def contar(texto: str) -> int:
    return len(tokenizar(texto))
