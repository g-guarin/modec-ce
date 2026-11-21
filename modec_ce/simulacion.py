"""
Experimento fuera de línea: misma carga MODEC en cuatro variantes.

  ingenua_volatil   metadatos arriba (patrón frecuente)
  ingenua_rol       rol del agente arriba (patrón frecuente)
  modec             mismo contenido, de lo estable a lo variable
  modec_compresion  modec + historial en Super-Tokens (cambia contenido; se mide fidelidad mecánica)

Cada variante corre con un caché vacío propio. Resultado: tokens estimados de acierto
y fallo de caché, costo derivado y ahorro relativo, con su procedencia.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import tokens
from .cache import REGLAS_ID, simular
from .carga import ConfigCarga, anclas_de, generar_peticiones, texto_historial, salida_sintetica
from .costo import cargar_tarifa

# El paquete MODEC original es opcional y no forma parte de este repositorio.
# `MODEC_CE_MODEC_SRC` apunta a su carpeta si se quiere comparar la réplica con el original.
_MODEC_SRC = os.environ.get("MODEC_CE_MODEC_SRC")
if _MODEC_SRC and Path(_MODEC_SRC).exists() and _MODEC_SRC not in sys.path:
    sys.path.insert(0, _MODEC_SRC)

VARIANTES = {
    "ingenua_volatil": ("ingenua_volatil", False),
    "ingenua_rol": ("ingenua_rol", False),
    "modec": ("modec", False),
    "modec_compresion": ("modec", True),
}


def _redondear(x: Decimal) -> str:
    return f"{x:.9f}"


def _medicion_c1_integrada(completo: str, comprimido: str, requeridas: list[str], preservadas: list[str]) -> dict:
    """Réplica de la métrica C.1 de MODEC, para quien no tenga el paquete MODEC original.
    Una prueba comprueba que da el mismo resultado que el instrumento original cuando este está presente."""
    fuente, resumen = tokens.contar(completo), tokens.contar(comprimido)
    req, pres = set(requeridas), set(preservadas)
    if not pres.issubset(req):
        raise ValueError("PRESERVED_ANCHOR_NOT_IN_REQUIRED_SET")
    return {
        "source_sha256": hashlib.sha256(completo.encode("utf-8")).hexdigest(),
        "summary_sha256": hashlib.sha256(comprimido.encode("utf-8")).hexdigest(),
        "source_tokens": fuente, "summary_tokens": resumen,
        "tokenizer_id": tokens.TOKENIZADOR_ID, "token_count_provenance": "DERIVED",
        "compression_ratio": resumen / fuente, "compression_savings_ratio": 1.0 - resumen / fuente,
        "required_anchor_count": len(req), "preserved_anchor_count": len(pres),
        "anchor_preservation_ratio": len(pres) / len(req) if req else None,
        "anchor_annotation_provenance": "DERIVED" if req else "NOT_EVALUATED",
        "fidelity_metric_id": "MODEC_ANCHOR_PRESERVATION_V1",
        "fidelity_interpretation": "MECHANICAL_ANCHOR_COVERAGE_NOT_SEMANTIC_VALIDITY",
    }


def medir_compresion(cfg: ConfigCarga, instrumento: str = "auto") -> dict[str, Any]:
    """Métrica C.1 de MODEC: cuánto se reduce el historial y si se conservan sus anclas.
    Usa el instrumento original de MODEC si está disponible (`MODEC_CE_MODEC_SRC`); si no, la
    réplica integrada. El campo `instrumento` declara cuál se usó."""
    entradas = [(a, p, salida_sintetica(cfg, a, p)) for p in range(1, cfg.pasos) for a in ("orquestador", *cfg.agentes)]
    completo = texto_historial(entradas, comprimir=False)
    comprimido = texto_historial(entradas, comprimir=True)
    requeridas = anclas_de(completo)
    preservadas = [a for a in anclas_de(comprimido) if a in set(requeridas)]
    original = None
    if instrumento in ("auto", "modec_core"):
        try:
            from modec_core.compression_metrics import measure_compression_and_anchor_preservation as original
        except ImportError:
            if instrumento == "modec_core":
                raise
    if original is None:
        return {**_medicion_c1_integrada(completo, comprimido, requeridas, preservadas),
                "instrumento": "modec_ce.simulacion (réplica integrada de C.1)"}
    m = original(
        completo, comprimido, token_counter=tokens.contar, tokenizer_id=tokens.TOKENIZADOR_ID,
        token_count_provenance="DERIVED", required_anchor_ids=requeridas, preserved_anchor_ids=preservadas,
        anchor_annotation_provenance="MEASURED")
    return {**m.to_dict(), "instrumento": "modec_core.compression_metrics (MODEC original)"}


def _acierto_por_bloques(acierto: int, minimo: int, bloque: int) -> int:
    """Regla genérica tipo OpenAI: sin caché bajo `minimo`; el resto se cuenta en múltiplos de `bloque`."""
    return 0 if acierto < minimo else (acierto // bloque) * bloque


def sensibilidad(agentes_opciones=(2, 4, 8), corpus_opciones=(1000, 4000, 12000), pasos: int = 3,
                 modelo: str = "deepseek-flash") -> dict[str, Any]:
    """Robustez del ahorro de `modec` frente a `ingenua_rol` al variar el tamaño de la carga.

    Se evalúan dos reglas de caché: la documentada por DeepSeek (R1–R3) y una regla genérica
    más restrictiva (mínimo 1 024 tokens, conteo en bloques de 128), aplicada a los mismos datos.
    """
    tarifa = cargar_tarifa(modelo, "peak")
    filas = []
    for n_ag in agentes_opciones:
        for corpus in corpus_opciones:
            cfg = ConfigCarga(pasos=pasos, agentes=tuple(f"agente{i}" for i in range(n_ag)), tokens_corpus=corpus,
                              secciones_corpus=max(4, corpus // 350))
            costos: dict[str, dict[str, Decimal]] = {}
            tasas: dict[str, float] = {}
            for brazo in ("ingenua_rol", "modec"):
                res = simular([p.texto for p in generar_peticiones(cfg, brazo, comprimir_historial=False)])
                total = sum(r.tokens_entrada for r in res)
                for regla, f in (("deepseek_doc", lambda h: h), ("generica_1024_128", lambda h: _acierto_por_bloques(h, 1024, 128))):
                    hit = sum(f(r.tokens_acierto) for r in res)
                    costos.setdefault(regla, {})[brazo] = tarifa.costo(hit, total - hit, 300 * len(res))
                    if regla == "deepseek_doc":
                        tasas[brazo] = round(hit / total, 4)
            filas.append({
                "agentes": n_ag, "tokens_corpus": corpus, "peticiones_por_brazo": pasos * (n_ag + 1),
                "acierto_ingenua_rol": tasas["ingenua_rol"], "acierto_modec": tasas["modec"],
                "ahorro": {regla: float(round((c["ingenua_rol"] - c["modec"]) / c["ingenua_rol"], 4))
                           for regla, c in costos.items()},
            })
    todos = [f["ahorro"][r] for f in filas for r in f["ahorro"]]
    return {"tipo": "SENSIBILIDAD_FUERA_DE_LINEA", "pasos": pasos, "modelo": modelo, "filas": filas,
            "ahorro_min": min(todos), "ahorro_max": max(todos),
            "procedencia": "ESTIMADO bajo las reglas de caché R1–R3 (R4 no modelada); no es una cota"}


def ejecutar(cfg: ConfigCarga | None = None, *, modelo: str = "deepseek-flash",
             tokens_salida: int = 300) -> dict[str, Any]:
    cfg = cfg or ConfigCarga()
    tarifas = {f: cargar_tarifa(modelo, f) for f in ("peak", "offpeak")}
    variantes: dict[str, Any] = {}
    huellas: dict[str, list[str]] = {}
    for nombre, (disposicion, comprimir) in VARIANTES.items():
        peticiones = generar_peticiones(cfg, disposicion, comprimir_historial=comprimir)
        huellas[nombre] = [p.huella_contenido for p in peticiones]
        resultados = simular([p.texto for p in peticiones])
        entrada = sum(r.tokens_entrada for r in resultados)
        acierto = sum(r.tokens_acierto for r in resultados)
        fallo = entrada - acierto
        salida = tokens_salida * len(peticiones)
        variantes[nombre] = {
            "peticiones": len(peticiones),
            "tokens_entrada": entrada,
            "tokens_acierto": acierto,
            "tokens_fallo": fallo,
            "tasa_acierto": round(acierto / entrada, 4) if entrada else None,
            "tokens_salida_supuestos": salida,
            "costo_usd": {f: _redondear(t.costo(acierto, fallo, salida)) for f, t in tarifas.items()},
            "por_peticion": [asdict(r) | {"paso": p.paso, "agente": p.agente}
                             for r, p in zip(resultados, peticiones)],
        }

    def ahorro(base: str, objetivo: str, franja: str) -> float:
        b = Decimal(variantes[base]["costo_usd"][franja])
        o = Decimal(variantes[objetivo]["costo_usd"][franja])
        return float(round((b - o) / b, 4)) if b else 0.0

    comparaciones = {
        f"{obj}_vs_{base}": {f: ahorro(base, obj, f) for f in ("peak", "offpeak")}
        for obj in ("modec", "modec_compresion") for base in ("ingenua_volatil", "ingenua_rol")
    }
    mismo_contenido = huellas["ingenua_volatil"] == huellas["ingenua_rol"] == huellas["modec"]
    return {
        "tipo": "SIMULACION_FUERA_DE_LINEA",
        "procedencia_tokens": f"{tokens.PROCEDENCIA} ({tokens.TOKENIZADOR_ID})",
        "procedencia_cache": f"ESTIMADO_BAJO_REGLAS_R1_R3_DOCUMENTADAS_R4_NO_MODELADA ({REGLAS_ID})",
        "procedencia_costo": f"DERIVADO de tarifa DECLARADA ({tarifas['peak'].referencia})",
        "modelo": modelo,
        "carga": cfg.a_dict(),
        "contenido_identico_entre_disposiciones": mismo_contenido,
        "variantes": variantes,
        "ahorro_relativo": comparaciones,
        "compresion_c1": medir_compresion(cfg),
        "advertencias": [
            "Simulación secuencial: en un fan-out paralelo real las peticiones simultáneas pueden no aprovechar "
            "unidades aún en construcción (la construcción del caché tarda segundos según la documentación).",
            "El caché del proveedor es de mejor esfuerzo; la tasa real solo la mide el piloto.",
            "La compresión en Super-Tokens cambia el contenido: la preservación de anclas es mecánica, "
            "no prueba equivalencia semántica.",
        ],
    }
