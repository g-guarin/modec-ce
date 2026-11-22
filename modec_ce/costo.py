"""
Costo derivado a partir de tarifas publicadas. Usa Decimal para no acumular error.

El costo calculado es DERIVADO de una tarifa DECLARADA por la fuente; no es la factura.
La conciliación con el panel del proveedor es el nivel de evidencia más alto.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

RUTA_PRECIOS = Path(__file__).resolve().parents[1] / "datos" / "precios.json"
MILLON = Decimal(1_000_000)


@dataclass(frozen=True)
class Tarifa:
    proveedor: str
    modelo: str
    franja: str
    acierto: Decimal
    fallo: Decimal
    salida: Decimal
    referencia: str
    escritura: Decimal | None = None

    def costo(self, tokens_acierto: int, tokens_fallo: int, tokens_salida: int, tokens_escritura: int = 0) -> Decimal:
        for n in (tokens_acierto, tokens_fallo, tokens_salida, tokens_escritura):
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise ValueError("los conteos de tokens deben ser enteros no negativos")
        precio_escritura = self.escritura if self.escritura is not None else self.fallo
        return (Decimal(tokens_acierto) * self.acierto + Decimal(tokens_fallo) * self.fallo
                + Decimal(tokens_escritura) * precio_escritura + Decimal(tokens_salida) * self.salida) / MILLON


def franjas(proveedor: str, modelo: str, ruta: Path = RUTA_PRECIOS) -> list[str]:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return list(datos["providers"][proveedor]["models"][modelo])


def cargar_tarifa(modelo: str = "deepseek-flash", franja: str | None = None, *, proveedor: str = "deepseek",
                  ruta: Path = RUTA_PRECIOS) -> Tarifa:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    try:
        modelos = datos["providers"][proveedor]["models"][modelo]
    except KeyError as exc:
        raise ValueError(f"sin tarifa registrada para {proveedor}/{modelo}; añádala a datos/precios.json") from exc
    franja = franja or ("peak" if "peak" in modelos else next(iter(modelos)))
    if franja not in modelos:
        raise ValueError(f"franja {franja} no disponible para {proveedor}/{modelo}")
    t = modelos[franja]
    # `cache_write` es opcional: sin él, Tarifa.costo cobra la escritura al precio de fallo.
    escritura = Decimal(t["cache_write"]) if "cache_write" in t else None
    return Tarifa(proveedor, modelo, franja, Decimal(t["cache_hit"]), Decimal(t["cache_miss"]),
                  Decimal(t["output"]), datos["reference_id"], escritura)
