"""
Piloto A/B real: misma carga, dos disposiciones, medición con el `usage` del proveedor.

Diseño (ajustado tras la primera propuesta):
  * Brazos: por defecto `ingenua_rol` (línea base fuerte) y `modec`, con el mismo contenido
    (se comprueba con la huella de contenido).
  * Corridas: por defecto 3. Cada corrida usa un nonce propio al inicio de todas las
    peticiones (aísla cachés de corridas anteriores) y alterna el orden de los brazos
    (AB, BA, AB…) para neutralizar efectos de orden.
  * Intercalado A1, B1, A2, B2… dentro de la corrida y pausa configurable entre llamadas
    (la documentación de DeepSeek indica que construir el caché tarda segundos).
  * Historial sintético y determinista: no se realimenta la salida del modelo, así el
    contenido sigue idéntico en ambos brazos.
  * Fallo cerrado: tope de llamadas, cota preflight (todo como fallo de caché a la tarifa
    más alta), parada ante el primer error HTTP, uso ausente (P2) o presupuesto superado.

La clave se lee de la variable de entorno del proveedor y nunca se escribe. No se guardan
prompts ni respuestas: solo huellas, conteos, latencias y costos, sellados con PESD P1.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import tokens
from .carga import ConfigCarga, generar_peticiones
from .costo import Tarifa, cargar_tarifa, franjas
from .evidencia import CadenaEvidencia
from .proveedores import PROVEEDORES, Proveedor, a_json, clave_de, url_de

CONFIRMACION = "EJECUTAR-PILOTO"

CONFIG_PILOTO = ConfigCarga(pasos=2, agentes=("analista", "auditor", "redactor"), tokens_corpus=3000,
                            tokens_salida_agente=400, secciones_corpus=10)


@dataclass(frozen=True)
class LimitesPiloto:
    max_llamadas: int = 60
    presupuesto_usd: Decimal = Decimal("0.50")
    max_tokens_salida: int = 64
    timeout_s: float = 90.0
    pausa_s: float = 1.5


@dataclass(frozen=True)
class LlamadaPlanificada:
    indice: int
    corrida: int
    brazo: str
    paso: int
    agente: str
    segmentos: tuple[str, ...]
    huella_contenido: str

    @property
    def texto(self) -> str:
        return "\n\n".join(self.segmentos)

    @property
    def huella_peticion(self) -> str:
        return hashlib.sha256(self.texto.encode("utf-8")).hexdigest()


Transporte = Callable[[str, Mapping[str, str], bytes, float], tuple[int, bytes]]


def transporte_urllib(url: str, cabeceras: Mapping[str, str], cuerpo: bytes, timeout: float) -> tuple[int, bytes]:
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1:")):
        raise PermissionError("solo se admiten URL https oficiales o el servidor local 127.0.0.1")
    req = urllib.request.Request(url, data=cuerpo, headers=dict(cabeceras), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - URL validada arriba
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def planificar(brazos: Sequence[str], cfg: ConfigCarga = CONFIG_PILOTO, corridas: int = 1,
               nonces: Sequence[str] | None = None) -> list[LlamadaPlanificada]:
    nonces = list(nonces) if nonces else [secrets.token_hex(8) for _ in range(corridas)]
    plan: list[LlamadaPlanificada] = []
    for c, nonce in enumerate(nonces):
        orden = list(brazos) if c % 2 == 0 else list(reversed(brazos))
        por_brazo = {b: generar_peticiones(cfg, b, comprimir_historial=False,
                                           volatil=lambda i, n=nonce: (f"REQ-{i:04d}-{n}", f"orden {i}"))
                     for b in orden}
        n = len(next(iter(por_brazo.values())))
        for i in range(n):
            for b in orden:
                p = por_brazo[b][i]
                segs = (f"EJECUCIÓN {nonce}",) + tuple(s.texto for s in p.segmentos)
                plan.append(LlamadaPlanificada(len(plan), c + 1, b, p.paso, p.agente, segs, p.huella_contenido))
    return plan


def tarifa_mas_alta(proveedor: str, modelo: str) -> Tarifa:
    tarifas = [cargar_tarifa(modelo, f, proveedor=proveedor) for f in franjas(proveedor, modelo)]
    return max(tarifas, key=lambda t: (t.fallo, t.escritura or 0, t.salida))


def cota_preflight(plan: Sequence[LlamadaPlanificada], tarifa: Tarifa, max_salida: int) -> Decimal:
    """Cota conservadora: bytes UTF-8 como tokens; todo como escritura o fallo, lo más caro."""
    total = Decimal(0)
    for ll in plan:
        entrada = len(ll.texto.encode("utf-8")) + 64
        total += max(tarifa.costo(0, entrada, max_salida), tarifa.costo(0, 0, max_salida, entrada))
    return total


@dataclass
class ResultadoPiloto:
    proveedor: str
    carpeta: Path
    llamadas: list[dict[str, Any]] = field(default_factory=list)
    detenido: str | None = None


def ejecutar_piloto(
    *,
    proveedor: str = "deepseek",
    modelo: str | None = None,
    brazos: Sequence[str] = ("ingenua_rol", "modec"),
    corridas: int = 3,
    limites: LimitesPiloto = LimitesPiloto(),
    carpeta_resultados: Path,
    cfg: ConfigCarga = CONFIG_PILOTO,
    clave: str | None = None,
    transporte: Transporte = transporte_urllib,
    confirmacion: str = "",
    opciones_modelo: Mapping[str, Any] | None = None,
    puerto_local: int | None = None,
    reloj: Callable[[], float] = time.perf_counter,
    dormir: Callable[[float], None] = time.sleep,
) -> ResultadoPiloto:
    if confirmacion != CONFIRMACION:
        raise PermissionError(f"Confirmación ausente: escriba {CONFIRMACION}")
    prov: Proveedor = PROVEEDORES[proveedor]
    modelo = modelo or prov.modelo_por_defecto
    clave = clave if clave is not None else clave_de(prov)
    if not clave:
        raise PermissionError(f"{prov.variable_clave} no está definida en este proceso")
    url = url_de(prov, puerto_local)
    plan = planificar(brazos, cfg, corridas)
    tarifas = {f: cargar_tarifa(modelo, f, proveedor=proveedor) for f in franjas(proveedor, modelo)}
    alta = tarifa_mas_alta(proveedor, modelo)
    if len(plan) > limites.max_llamadas:
        raise PermissionError(f"El plan requiere {len(plan)} llamadas; el tope es {limites.max_llamadas}")
    cota = cota_preflight(plan, alta, limites.max_tokens_salida)
    if cota > limites.presupuesto_usd:
        raise PermissionError(f"Cota preflight USD {cota:.6f} supera el presupuesto USD {limites.presupuesto_usd}")

    marca = time.strftime("%Y%m%d_%H%M%S")
    carpeta = carpeta_resultados / f"piloto_{proveedor}_{marca}_{secrets.token_hex(3)}"
    carpeta.mkdir(parents=True, exist_ok=True)
    cadena = CadenaEvidencia(carpeta / "evidencia.jsonl")
    res = ResultadoPiloto(proveedor, carpeta)
    opciones = dict(opciones_modelo if opciones_modelo is not None else prov.opciones_por_defecto)
    acumulado = Decimal(0)
    cadena.asentar({"tipo": "PLAN", "proveedor": proveedor, "modelo": modelo, "brazos": list(brazos),
                    "corridas": corridas, "llamadas_planificadas": len(plan), "cota_preflight_usd": f"{cota:.9f}",
                    "presupuesto_usd": str(limites.presupuesto_usd), "tarifa": alta.referencia,
                    "pausa_s": limites.pausa_s, "max_tokens_salida": limites.max_tokens_salida,
                    "carga": cfg.a_dict(), "contenido_identico": _contenido_identico(plan, brazos),
                    "motor_evidencia": cadena.motor_evidencia})

    for ll in plan:
        cuerpo = a_json(prov.cuerpo(modelo, ll.segmentos, limites.max_tokens_salida, opciones))
        t0 = reloj()
        try:
            estado, crudo = transporte(url, prov.cabeceras(clave), cuerpo, limites.timeout_s)
            error = None
        except PermissionError:
            raise
        except Exception as exc:  # noqa: BLE001 - se registra y se detiene
            estado, crudo, error = 0, b"", f"{type(exc).__name__}: {exc}"
        latencia_ms = round((reloj() - t0) * 1000, 1)
        datos: dict[str, Any] = {}
        if crudo:
            try:
                datos = json.loads(crudo.decode("utf-8"))
            except ValueError:
                error = error or "respuesta no JSON"
        usage = datos.get("usage") if isinstance(datos, dict) else None
        uso = prov.normalizar(usage)
        evaluable = estado == 200 and uso.evaluable
        fila: dict[str, Any] = {
            "tipo": "LLAMADA", "indice": ll.indice, "corrida": ll.corrida, "brazo": ll.brazo, "paso": ll.paso,
            "agente": ll.agente, "proveedor": proveedor, "modelo": modelo, "http": estado,
            "latencia_ms": latencia_ms, "huella_peticion": ll.huella_peticion,
            "huella_contenido": ll.huella_contenido, "tokens_estimados": tokens.contar(ll.texto),
            "presencia_uso": uso.presencia, "evaluable": evaluable,
            "error": error or (None if estado == 200 else _error_de(datos)),
        }
        if evaluable:
            fila.update(acierto=uso.acierto, escritura=uso.escritura, fallo=uso.fallo, salida=uso.salida,
                        costos_usd={f: f"{t.costo(uso.acierto, uso.fallo, uso.salida, uso.escritura):.9f}"
                                    for f, t in tarifas.items()},
                        costo_plataforma_usd=uso.costo_plataforma)
            if isinstance(usage, dict) and isinstance(usage.get("prefill_ms"), (int, float)):
                fila["prefill_ms"] = usage["prefill_ms"]
            fila["huella_respuesta"] = hashlib.sha256(prov.texto_respuesta(datos).encode("utf-8")).hexdigest()
            acumulado += alta.costo(uso.acierto, uso.fallo, uso.salida, uso.escritura)
        cadena.asentar(fila)
        res.llamadas.append(fila)
        if not evaluable:
            res.detenido = f"llamada {ll.indice}: {'uso ausente o incompleto (P2)' if estado == 200 else fila['error']}"
            break
        if acumulado > limites.presupuesto_usd:
            res.detenido = f"costo derivado acumulado USD {acumulado:.6f} supera el presupuesto"
            break
        if limites.pausa_s:
            dormir(limites.pausa_s)

    resumen = resumir(res.llamadas, brazos)
    resumen.update(proveedor=proveedor, modelo=modelo, detenido=res.detenido, verificacion=cadena.verificar())
    if proveedor == "local":
        resumen["ahorro_equivalente_deepseek"] = ahorro_equivalente(res.llamadas, brazos,
                                                                    cargar_tarifa("deepseek-flash", "peak"))
        resumen["procedencia"] = ("MEDIDO en transformador local (tokens y latencia); el proveedor local no cobra: "
                                  "ver ahorro_equivalente_deepseek")
    cadena.asentar({"tipo": "RESUMEN", **{k: v for k, v in resumen.items() if k != "verificacion"}})
    resumen["verificacion"] = cadena.verificar()
    (carpeta / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def _contenido_identico(plan: Sequence[LlamadaPlanificada], brazos: Sequence[str]) -> bool:
    for c in {ll.corrida for ll in plan}:
        por_brazo = [[ll.huella_contenido for ll in plan if ll.brazo == b and ll.corrida == c] for b in brazos]
        if any(v != por_brazo[0] for v in por_brazo):
            return False
    return True


def _error_de(datos: Any) -> str:
    if isinstance(datos, dict) and isinstance(datos.get("error"), dict):
        e = datos["error"]
        return f"{e.get('type', 'error')}: {e.get('message', '')}"[:300]
    return "error HTTP sin detalle"


def _totales(filas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hit = sum(f["acierto"] for f in filas)
    esc = sum(f["escritura"] for f in filas)
    miss = sum(f["fallo"] for f in filas)
    entrada = hit + esc + miss
    franjas_ = list(filas[0]["costos_usd"]) if filas else []
    lat = [f["latencia_ms"] for f in filas]
    pre = [f["prefill_ms"] for f in filas if "prefill_ms" in f]
    return {
        "llamadas_medidas": len(filas), "tokens_acierto": hit, "tokens_escritura": esc, "tokens_fallo": miss,
        "tasa_acierto": round(hit / entrada, 4) if entrada else None,
        "costos_usd": {fr: f"{sum(Decimal(f['costos_usd'][fr]) for f in filas):.9f}" for fr in franjas_},
        "latencia_mediana_ms": statistics.median(lat) if lat else None,
        "latencia_total_ms": round(sum(lat), 1),
        "prefill_total_ms": round(sum(pre), 1) if pre else None,
    }


def ahorro_equivalente(llamadas: Sequence[Mapping[str, Any]], brazos: Sequence[str], tarifa: Tarifa) -> dict[str, Any]:
    """Aplica una tarifa de referencia a los tokens MEDIDOS (útil para el piloto local, que no cobra)."""
    medidas = [f for f in llamadas if f.get("evaluable")]
    salida: dict[str, Any] = {"tarifa": f"{tarifa.proveedor}/{tarifa.modelo}/{tarifa.franja} ({tarifa.referencia})",
                              "procedencia": "tokens MEDIDOS + costo DERIVADO de tarifa DECLARADA", "corridas": {}}
    valores = []
    for c in sorted({f["corrida"] for f in medidas}):
        costos = {b: sum((tarifa.costo(f["acierto"], f["fallo"], f["salida"], f["escritura"])
                          for f in medidas if f["corrida"] == c and f["brazo"] == b), Decimal(0)) for b in brazos}
        a, b = (costos[x] for x in brazos[:2])
        if a:
            valores.append(float(round((a - b) / a, 4)))
            salida["corridas"][str(c)] = valores[-1]
    if valores:
        salida.update(media=round(statistics.mean(valores), 4), min=min(valores), max=max(valores))
    return salida


def resumir(llamadas: Sequence[Mapping[str, Any]], brazos: Sequence[str]) -> dict[str, Any]:
    medidas = [f for f in llamadas if f.get("evaluable")]
    corridas = sorted({f["corrida"] for f in medidas})
    out: dict[str, Any] = {"brazos": {b: _totales([f for f in medidas if f["brazo"] == b]) for b in brazos},
                           "corridas": {}}
    ahorros: list[float] = []
    for c in corridas:
        tot = {b: _totales([f for f in medidas if f["brazo"] == b and f["corrida"] == c]) for b in brazos}
        fila: dict[str, Any] = {"brazos": tot}
        if len(brazos) == 2:
            a, b = (tot[x] for x in brazos)
            if a["llamadas_medidas"] and a["llamadas_medidas"] == b["llamadas_medidas"]:
                fr = next(iter(a["costos_usd"]))
                ca, cb = Decimal(a["costos_usd"][fr]), Decimal(b["costos_usd"][fr])
                if ca:
                    fila["ahorro_relativo"] = float(round((ca - cb) / ca, 4))
                    ahorros.append(fila["ahorro_relativo"])
                if a["latencia_total_ms"]:
                    fila["reduccion_latencia"] = round(1 - b["latencia_total_ms"] / a["latencia_total_ms"], 4)
        out["corridas"][str(c)] = fila
    if ahorros:
        out["ahorro_relativo"] = {"media": round(statistics.mean(ahorros), 4), "min": min(ahorros),
                                  "max": max(ahorros), "corridas_validas": len(ahorros)}
        out["criterio_30pct_todas"] = all(a >= 0.30 for a in ahorros)
        out["procedencia"] = "MEDIDO (usage del proveedor) + costo DERIVADO de tarifa DECLARADA"
    else:
        out["ahorro_relativo"] = None
        out["procedencia"] = "NO_EVALUABLE"
    return out
