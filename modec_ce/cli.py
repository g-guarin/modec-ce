"""
Línea de comandos de MODEC-CE.

  simular                     experimento fuera de línea (JSON + informe)
  sensibilidad                robustez del ahorro al variar agentes y corpus (fuera de línea)
  piloto-local                piloto completo contra un transformador local real (sin clave, sin costo)
  piloto --plan               plan, llamadas y cota de costo para un proveedor (sin red)
  piloto --ejecutar           piloto real (clave en variable de entorno y --confirmar EJECUTAR-PILOTO)
  verificar <carpeta>         recalcula y verifica la cadena de evidencia de un piloto
  informe                     informe HTML consolidado con todo lo que hay en resultados/
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from decimal import Decimal
from pathlib import Path

from . import simulacion
from .carga import ConfigCarga
from .evidencia import CadenaEvidencia
from .informe import generar_html
from .piloto import (CONFIG_PILOTO, CONFIRMACION, LimitesPiloto, cota_preflight, ejecutar_piloto, planificar,
                     tarifa_mas_alta)
from .proveedores import PROVEEDORES

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados"


def _leer(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _escribir(nombre: str, datos) -> None:
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / nombre).write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_simular(_args) -> int:
    sim = simulacion.ejecutar()
    _escribir("simulacion.json", sim)
    for nombre, v in sim["variantes"].items():
        print(f"{nombre:<18} entrada={v['tokens_entrada']:>8,}  acierto={v['tasa_acierto']:.1%}  "
              f"costo_peak=${Decimal(v['costo_usd']['peak']):.6f}")
    for k, v in sim["ahorro_relativo"].items():
        print(f"ahorro {k:<38} {v['peak']:.1%}")
    return cmd_informe(None)


def cmd_sensibilidad(_args) -> int:
    s = simulacion.sensibilidad()
    _escribir("sensibilidad.json", s)
    print(f"ahorro estimado de modec frente a ingenua_rol: {s['ahorro_min']:.1%} a {s['ahorro_max']:.1%}")
    return cmd_informe(None)


def _limites(args) -> LimitesPiloto:
    return LimitesPiloto(max_llamadas=args.max_llamadas, presupuesto_usd=Decimal(args.presupuesto),
                         max_tokens_salida=args.max_salida, pausa_s=args.pausa)


def cmd_piloto(args) -> int:
    prov = PROVEEDORES[args.proveedor]
    modelo = args.modelo or prov.modelo_por_defecto
    brazos = tuple(args.brazos.split(","))
    limites = _limites(args)
    if not args.ejecutar:
        plan = planificar(brazos, CONFIG_PILOTO, args.corridas)
        cota = cota_preflight(plan, tarifa_mas_alta(args.proveedor, modelo), limites.max_tokens_salida)
        print(f"Proveedor {args.proveedor} · modelo {modelo} · {args.corridas} corridas · {len(plan)} llamadas. Sin red.")
        print(f"Cota preflight (todo sin caché, tarifa más alta): USD {cota:.6f}")
        print(f"Tope de llamadas: {limites.max_llamadas}; presupuesto: USD {limites.presupuesto_usd}")
        ok = len(plan) <= limites.max_llamadas and cota <= limites.presupuesto_usd
        print("Resultado: " + ("DENTRO DE LOS TOPES" if ok else "FUERA DE LOS TOPES"))
        return 0 if ok else 2
    res = ejecutar_piloto(proveedor=args.proveedor, modelo=modelo, brazos=brazos, corridas=args.corridas,
                          limites=limites, carpeta_resultados=RESULTADOS, confirmacion=args.confirmar or "")
    return _cerrar(res)


def cmd_piloto_local(args) -> int:
    from .servidor_local import ServicioLocal, crear_servidor

    servicio = ServicioLocal()
    servidor = crear_servidor(servicio)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        cfg = ConfigCarga(pasos=2, agentes=("analista", "auditor", "redactor"), tokens_corpus=args.corpus,
                          tokens_salida_agente=300, secciones_corpus=8)
        res = ejecutar_piloto(proveedor="local", brazos=tuple(args.brazos.split(",")), corridas=args.corridas,
                              limites=LimitesPiloto(max_llamadas=200, pausa_s=0), carpeta_resultados=RESULTADOS,
                              cfg=cfg, confirmacion=CONFIRMACION, puerto_local=servidor.server_address[1])
    finally:
        servidor.shutdown()
        servidor.server_close()
    return _cerrar(res)


def _cerrar(res) -> int:
    resumen = _leer(res.carpeta / "resumen.json")
    print(json.dumps({k: resumen.get(k) for k in ("proveedor", "modelo", "ahorro_relativo", "criterio_30pct_todas",
                                                   "procedencia", "detenido")}, indent=2, ensure_ascii=False))
    for c, d in resumen["corridas"].items():
        print(f"corrida {c}: ahorro {d.get('ahorro_relativo')}  reducción de latencia {d.get('reduccion_latencia')}")
    print(f"cadena de evidencia íntegra: {resumen['verificacion']['integra']}  ({res.carpeta})")
    cmd_informe(None)
    return 0 if res.detenido is None else 3


def cmd_verificar(args) -> int:
    resultado = CadenaEvidencia(Path(args.carpeta) / "evidencia.jsonl").verificar()
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado["integra"] else 1


def cmd_informe(_args) -> int:
    sim = _leer(RESULTADOS / "simulacion.json")
    if sim is None:
        sim = simulacion.ejecutar()
        _escribir("simulacion.json", sim)
    pilotos = [r for r in (_leer(p / "resumen.json") for p in sorted(RESULTADOS.glob("piloto_*"))) if r]
    destino = RESULTADOS / "informe.html"
    destino.write_text(generar_html(sim, pilotos, _leer(RESULTADOS / "sensibilidad.json")), encoding="utf-8")
    print(f"informe: {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="modec_ce", description="MODEC-CE: costo y evidencia para orquestación LLM")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("simular").set_defaults(f=cmd_simular)
    sub.add_parser("sensibilidad").set_defaults(f=cmd_sensibilidad)
    pl = sub.add_parser("piloto-local")
    pl.add_argument("--corridas", type=int, default=3)
    pl.add_argument("--corpus", type=int, default=2000)
    pl.add_argument("--brazos", default="ingenua_rol,modec")
    pl.set_defaults(f=cmd_piloto_local)
    pp = sub.add_parser("piloto")
    pp.add_argument("--proveedor", default="deepseek", choices=[k for k in PROVEEDORES if k != "local"])
    pp.add_argument("--modelo")
    pp.add_argument("--ejecutar", action="store_true", help="llamadas reales al proveedor")
    pp.add_argument("--confirmar", help=f"escriba {CONFIRMACION} para autorizar las llamadas")
    pp.add_argument("--brazos", default="ingenua_rol,modec")
    pp.add_argument("--corridas", type=int, default=3)
    pp.add_argument("--max-llamadas", type=int, default=60)
    pp.add_argument("--presupuesto", default="0.50", help="USD, tope del lote")
    pp.add_argument("--max-salida", type=int, default=64)
    pp.add_argument("--pausa", type=float, default=1.5, help="segundos entre llamadas")
    pp.set_defaults(f=cmd_piloto)
    pv = sub.add_parser("verificar")
    pv.add_argument("carpeta")
    pv.set_defaults(f=cmd_verificar)
    sub.add_parser("informe").set_defaults(f=cmd_informe)
    args = p.parse_args(argv)
    try:
        return args.f(args)
    except PermissionError as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
