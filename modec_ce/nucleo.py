"""
Acceso al núcleo de evidencia.

Con `pesd-nucleo` (núcleo propietario, opcional y no incluido) disponible en `MODEC_CE_PESD_SRC`,
MODEC-CE lo usa para sellar y verificar la evidencia.

Sin él, MODEC-CE funciona igual con una **cadena mínima integrada**: JSON ordenado + SHA-256
encadenado + HMAC opcional. Es una cadena de integridad genérica. Cada resultado declara
qué motor lo selló (`motor_evidencia`).

`MODEC_CE_SIN_PESD=1` fuerza la cadena mínima aunque el núcleo esté disponible.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


def _rutas_candidatas() -> list[str]:
    rutas = []
    if os.environ.get("MODEC_CE_PESD_SRC"):
        rutas.append(os.environ["MODEC_CE_PESD_SRC"])
    return rutas


# `Any` a propósito: el núcleo propietario es opcional y no está en el clon público, así que su
# tipo no se puede comprobar aquí. Anotarlo como Any evita que el verificador de tipos trate
# `PESD` como None y declare inalcanzable todo el camino con núcleo disponible.
PESD: Any = None
if os.environ.get("MODEC_CE_SIN_PESD") != "1":
    for _r in _rutas_candidatas():
        if Path(_r).exists() and _r not in sys.path:
            sys.path.insert(0, _r)
            break
    try:
        import pesd_nucleo as PESD  # type: ignore[no-redef]
        # Sonda de disponibilidad: si este submódulo falta, el except deja PESD en None.
        from pesd_nucleo.p1_sellado import RegistroSellado as _RegistroPESD  # noqa: F401
        from pesd_nucleo.p2_centinela import Registro as _RegistroP2, registro as _registro_p2
    except ImportError:
        PESD = None

DISPONIBLE = PESD is not None
VERSION_NUCLEO: str | None = getattr(PESD, "__version__", None)
FORMATO_MINIMO = "modec-ce-cadena-minima-v1"


# ------------------------------------------------------------------ P2: presencia ternaria

class _RegistroMinimo(Enum):
    AUSENTE = "AUSENTE"
    NO_APLICA = "NO_APLICA"
    VACIO = "VACIO"
    PRESENTE = "PRESENTE"


_FALTA = object()


def _resolver(datos: Mapping[str, Any], ruta: str | Sequence[str]) -> Any:
    actual: Any = datos
    for p in (ruta.split(".") if isinstance(ruta, str) else ruta):
        if not isinstance(actual, Mapping) or p not in actual:
            return _FALTA
        actual = actual[p]
    return actual


def registro_minimo(datos: Mapping[str, Any], ruta: str | Sequence[str]) -> _RegistroMinimo:
    """Misma clasificación que la política por defecto de P2: 0 y False son PRESENTE."""
    v = _resolver(datos, ruta)
    if v is _FALTA:
        return _RegistroMinimo.AUSENTE
    if v is None:
        return _RegistroMinimo.VACIO
    if isinstance(v, bool):
        return _RegistroMinimo.PRESENTE
    if isinstance(v, float) and math.isnan(v):
        return _RegistroMinimo.VACIO
    if isinstance(v, str) and not v.strip():
        return _RegistroMinimo.VACIO
    if isinstance(v, (bytes, bytearray, list, tuple, dict, set, frozenset)) and len(v) == 0:
        return _RegistroMinimo.VACIO
    return _RegistroMinimo.PRESENTE


if DISPONIBLE:
    Registro = _RegistroP2
    registro = _registro_p2
else:
    Registro = _RegistroMinimo  # type: ignore[misc,assignment]
    registro = registro_minimo  # type: ignore[assignment]


# ------------------------------------------------------------------ P1: cadena mínima

def _canon(x: Any) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


class RegistroMinimo:
    """Eslabón de la cadena mínima. `payload` tiene la misma semántica que en PESD."""

    __slots__ = ("secuencia", "hash_previo", "payload", "key_id", "hmac", "digest")

    def __init__(self, secuencia: int, hash_previo: str | None, payload: dict, key_id: str | None,
                 hmac_hex: str | None, digest: str):
        self.secuencia, self.hash_previo, self.payload = secuencia, hash_previo, payload
        self.key_id, self.hmac, self.digest = key_id, hmac_hex, digest

    def cuerpo(self) -> dict:
        return {"formato": FORMATO_MINIMO, "secuencia": self.secuencia, "hash_previo": self.hash_previo,
                "payload": self.payload, "key_id": self.key_id}

    def a_json(self) -> str:
        return _canon({**self.cuerpo(), "hmac": self.hmac, "digest": self.digest}).decode("utf-8")

    @staticmethod
    def desde_json(texto: str) -> "RegistroMinimo":
        d = json.loads(texto)
        return RegistroMinimo(d["secuencia"], d["hash_previo"], d["payload"], d.get("key_id"), d.get("hmac"),
                              d["digest"])


class CadenaMinima:
    """Sella y verifica sin el núcleo PESD. Detecta alteración, borrado intermedio y reordenación;
    sin ancla externa no detecta el truncamiento de la cola (igual que PESD sin ancla).

    Verificación con clave = MODO ESTRICTO: si se entrega clave, se exige que TODO registro
    traiga `key_id` esperado y un HMAC válido. Sin esa exigencia la autenticidad sería
    degradable: como `key_id` va dentro del cuerpo digestado, quien reescriba la cadena podría
    quitar `key_id` y `hmac` de cada registro, recalcular los digest y pasar la verificación
    limpia. Un control que no reclama lo ausente contradice P2."""

    def __init__(self, clave: bytes | None, key_id: str):
        self.clave, self.key_id = clave, key_id

    def sellar(self, payload: Mapping[str, Any], anterior: RegistroMinimo | None) -> RegistroMinimo:
        p = json.loads(_canon(dict(payload)))
        r = RegistroMinimo(0 if anterior is None else anterior.secuencia + 1,
                           None if anterior is None else anterior.digest, p,
                           self.key_id if self.clave else None, None, "")
        cuerpo = _canon(r.cuerpo())
        r.digest = hashlib.sha256(cuerpo).hexdigest()
        if self.clave:
            r.hmac = hmac.new(self.clave, cuerpo, hashlib.sha256).hexdigest()
        return r

    def verificar(self, registros: Sequence[RegistroMinimo]) -> tuple[list[str], list[str]]:
        motivos: list[str] = []
        previo: str | None = None
        for i, r in enumerate(registros):
            cuerpo = _canon(r.cuerpo())
            if hashlib.sha256(cuerpo).hexdigest() != r.digest:
                motivos.append(f"[{i}] digest no coincide (contenido alterado)")
            if r.secuencia != i:
                motivos.append(f"[{i}] secuencia {r.secuencia} != {i}")
            if r.hash_previo != previo:
                motivos.append(f"[{i}] enlace hash_previo roto")
            if self.clave:                                   # modo estricto: la firma no es opcional
                if not r.key_id:
                    motivos.append(f"[{i}] registro sin HMAC: con clave se exige firma en todos los registros")
                elif r.key_id != self.key_id:
                    motivos.append(f"[{i}] key_id {r.key_id!r} distinto del esperado {self.key_id!r}")
                elif not hmac.compare_digest(hmac.new(self.clave, cuerpo, hashlib.sha256).hexdigest(), r.hmac or ""):
                    motivos.append(f"[{i}] HMAC inválido")
            elif r.key_id:
                motivos.append(f"[{i}] registro con HMAC y sin clave para verificarlo")
            previo = r.digest
        limites = ["SIN ANCLA: el truncamiento de la cola y la reescritura total no son detectables",
                   "CADENA MÍNIMA: integridad genérica, sin el motor de evidencia opcional del núcleo propietario"]
        if not self.clave:
            limites.append("SIN CLAVE: solo integridad. La clave es la declaración de qué firma se espera; "
                           "sin entregarla, una cadena a la que se le quitaron las firmas verifica igual")
        return motivos, limites


def es_formato_minimo(linea: str) -> bool:
    try:
        return json.loads(linea).get("formato") == FORMATO_MINIMO
    except (ValueError, AttributeError):
        return False


__all__ = ["DISPONIBLE", "VERSION_NUCLEO", "PESD", "Registro", "registro", "registro_minimo",
           "CadenaMinima", "RegistroMinimo", "es_formato_minimo", "FORMATO_MINIMO"]
if DISPONIBLE:
    __all__.append("_RegistroPESD")
