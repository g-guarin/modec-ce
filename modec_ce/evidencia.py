"""
Evidencia sellada de cada medición: núcleo PESD 2.0.0 si está disponible; si no, cadena mínima integrada.

  P2  El uso informado por el proveedor se clasifica por presencia: un campo de caché
      AUSENTE no es "0 aciertos". Si falta, la medición queda NO_EVALUABLE.
  P1  Cada medición se sella en cadena (SHA-256 + hash_previo; HMAC si hay clave).
      Un tercero puede verificar la cadena sin confiar en este programa.

No se guardan prompts ni respuestas: solo conteos, costos, latencias y huellas SHA-256.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import nucleo
from .nucleo import Registro, registro  # noqa: F401  (reexportados para proveedores.py)

VERSION_NUCLEO = nucleo.VERSION_NUCLEO
CAMPOS_USO = ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
KEY_ID = "modec-ce"


def motor_evidencia() -> str:
    return f"pesd-nucleo {VERSION_NUCLEO}" if nucleo.DISPONIBLE else nucleo.FORMATO_MINIMO


def presencia_uso(usage: Mapping[str, Any] | None) -> dict[str, str]:
    """Estado P2 de cada campo de uso: PRESENTE, AUSENTE, VACIO."""
    datos = dict(usage or {})
    return {c: registro(datos, c).name for c in CAMPOS_USO}


def uso_evaluable(usage: Mapping[str, Any] | None) -> bool:
    estados = presencia_uso(usage)
    if any(estados[c] != "PRESENTE" for c in CAMPOS_USO):
        return False
    return all(isinstance(usage[c], int) and not isinstance(usage[c], bool) and usage[c] >= 0 for c in CAMPOS_USO)


def _clave_desde_entorno() -> bytes | None:
    clave = os.environ.get("MODEC_CE_CLAVE_HEX")
    if not clave:
        return None
    b = bytes.fromhex(clave.strip())
    if len(b) < 32:
        raise ValueError("MODEC_CE_CLAVE_HEX debe tener al menos 32 bytes (64 caracteres hexadecimales)")
    return b


class CadenaEvidencia:
    """Bitácora JSONL de registros sellados en cadena (núcleo PESD o cadena mínima integrada).

    El motor se fija por archivo: una bitácora creada con PESD se verifica con PESD, y una creada con la
    cadena mínima, con la cadena mínima.
    """

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.clave = _clave_desde_entorno()
        primera = self._primera_linea()
        self.minima = (primera is not None and nucleo.es_formato_minimo(primera)) or (
            primera is None and not nucleo.DISPONIBLE)
        if self.minima:
            self._motor_min = nucleo.CadenaMinima(self.clave, KEY_ID)
        elif nucleo.DISPONIBLE:
            self.llavero = None
            if self.clave:
                self.llavero = nucleo.PESD.Llavero()
                self.llavero.agregar(KEY_ID, self.clave)
            self.motor = nucleo.PESD.MotorSellado(self.llavero)
        self._ultimo: Any = None
        if primera is not None and (self.minima or nucleo.DISPONIBLE):
            for r in self.leer():
                self._ultimo = r

    @property
    def motor_evidencia(self) -> str:
        return nucleo.FORMATO_MINIMO if self.minima else f"pesd-nucleo {VERSION_NUCLEO}"

    def _primera_linea(self) -> str | None:
        if not self.ruta.exists():
            return None
        for linea in self.ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                return linea
        return None

    def leer(self) -> list[Any]:
        if not self.ruta.exists():
            return []
        lineas = [x for x in self.ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
        if self.minima:
            return [nucleo.RegistroMinimo.desde_json(x) for x in lineas]
        if not nucleo.DISPONIBLE:
            raise RuntimeError("esta bitácora fue sellada con pesd-nucleo; instálelo o defina MODEC_CE_PESD_SRC")
        return [nucleo._RegistroPESD.desde_json(x) for x in lineas]

    def asentar(self, payload: Mapping[str, Any]) -> Any:
        if self.minima:
            r = self._motor_min.sellar(payload, self._ultimo)
        else:
            if not nucleo.DISPONIBLE:
                raise RuntimeError("esta bitácora fue sellada con pesd-nucleo; instálelo o defina MODEC_CE_PESD_SRC")
            r = self.motor.sellar(dict(payload), key_id=KEY_ID if self.llavero else None, anterior=self._ultimo)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(r.a_json() + "\n")
        self._ultimo = r
        return r

    def verificar(self) -> dict[str, Any]:
        base = {"motor_evidencia": self.motor_evidencia,
                "autenticidad": "HMAC" if self.clave else "NINGUNA (sin clave: solo integridad)"}
        if not self.minima and not nucleo.DISPONIBLE:
            return {**base, "registros": None, "integra": False, "estado_minimo": None,
                    "motivos": ["NO_EVALUABLE: bitácora sellada con pesd-nucleo, que no está disponible"],
                    "limites": [], "nucleo_pesd": None}
        registros = self.leer()
        if self.minima:
            motivos, limites = self._motor_min.verificar(registros)
            estado = None
        else:
            ivp = nucleo.PESD.ProcedimientoVerificacionIndependiente(llavero=self.llavero)
            informe = ivp.verificar_cadena(registros)
            motivos = list(getattr(informe, "motivos", []) or [])
            limites = list(getattr(informe, "limites", []) or [])
            e = getattr(informe, "estado_sello", None)
            estado = e.name if e is not None else None
        return {**base, "registros": len(registros), "integra": not motivos and bool(registros),
                "estado_minimo": estado, "motivos": motivos, "limites": limites,
                "nucleo_pesd": None if self.minima else VERSION_NUCLEO}


def leer_payloads(registros: Iterable[Any]) -> list[dict[str, Any]]:
    return [json.loads(json.dumps(r.payload)) for r in registros]
