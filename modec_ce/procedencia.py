"""
Procedencia temporal y de código de cada corrida sellada.

El sello de la cadena ata contenido y orden. Por sí solo no dice CUÁNDO se produjo la
medición ni CON QUÉ CÓDIGO: sin esos dos datos dentro del payload, un tercero puede
comprobar que la bitácora no fue alterada, pero no puede fecharla ni atarla a una
versión publicada del programa. Este módulo los aporta para que viajen dentro del sello.

Coherente con P2 (presencia ternaria): si el dato no está disponible —por ejemplo, el
paquete instalado sin repositorio git— el campo queda en `null` y `procedencia_codigo`
lo declara AUSENTE. Nunca se inventa un valor ni se sustituye por un cero.

Límite que esto NO resuelve: la fecha la pone el propio equipo que corre el piloto, así
que acredita la hora declarada por el autor, no una hora certificada por un tercero. El
ancla externa (sello de tiempo RFC 3161 sobre el digest final) es lo que convierte esa
fecha declarada en fecha verificable.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from . import __version__

RAIZ = Path(__file__).resolve().parents[1]


def ahora_utc() -> str:
    """Instante actual en UTC, ISO 8601 con segundos."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git(*args: str) -> str | None:
    """Salida de un comando git en la raíz del proyecto, o None si no se puede obtener."""
    try:
        r = subprocess.run(("git", "-C", str(RAIZ), *args), capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def procedencia_codigo() -> dict[str, Any]:
    """Versión del paquete y commit del árbol que ejecuta.

    `arbol_limpio` es decisivo: con el árbol sucio el commit NO identifica el código que
    corrió, y quien audite debe saberlo.
    """
    commit = _git("rev-parse", "HEAD")
    estado = _git("status", "--porcelain")
    return {
        "version_modec_ce": __version__,
        "commit": commit,
        "arbol_limpio": None if estado is None else estado == "",
        "procedencia_codigo": "MEDIDO (git)" if commit else "AUSENTE (sin repositorio git disponible)",
    }


def sello_corrida() -> dict[str, Any]:
    """Bloque de procedencia que se asienta en el registro PLAN de cada corrida."""
    return {"fecha_utc": ahora_utc(), "procedencia_fecha": "DECLARADA por el equipo que ejecuta; "
            "sin ancla externa no es una fecha certificada por un tercero", **procedencia_codigo()}


__all__ = ["ahora_utc", "procedencia_codigo", "sello_corrida", "RAIZ"]
