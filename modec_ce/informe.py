"""Informe HTML autocontenido (sin recursos externos): simulación, sensibilidad y pilotos."""
from __future__ import annotations

import html
from decimal import Decimal
from typing import Any, Mapping, Sequence

ETIQUETAS = {
    "ingenua_volatil": "Ingenua · metadatos arriba",
    "ingenua_rol": "Ingenua · rol arriba",
    "modec": "MODEC-CE · estable→variable",
    "modec_compresion": "MODEC-CE + Super-Tokens",
}

_CSS = """
:root{--fondo:#f7f7f5;--texto:#1d1d1b;--suave:#5f5f5a;--borde:#d9d9d4;--a:#2f6f5e;--b:#b8603c;--tarjeta:#fff}
@media (prefers-color-scheme:dark){:root{--fondo:#151515;--texto:#ececea;--suave:#a5a5a0;--borde:#333;--a:#5fb39b;--b:#e08a63;--tarjeta:#1e1e1e}}
body{margin:0;background:var(--fondo);color:var(--texto);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}h3{font-size:15px;margin:4px 0 8px}
p,li{color:var(--suave)}.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:16px;margin:12px 0;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--borde)}
th{color:var(--suave);font-weight:600}.barra{height:12px;border-radius:3px;background:var(--b)}.barra.mejor{background:var(--a)}
.cifra{font-size:28px;font-weight:700;color:var(--a)}.kpis{display:flex;gap:12px;flex-wrap:wrap}.kpis .tarjeta{flex:1;min-width:180px}
code{font-size:13px}
"""


def _pct(x: Any) -> str:
    return "—" if x is None else f"{x:.1%}"


def _fila_variante(nombre: str, v: Mapping[str, Any], maximo: Decimal) -> str:
    costo = Decimal(v["costo_usd"]["peak"])
    ancho = float(costo / maximo * 100) if maximo else 0
    clase = "barra mejor" if nombre.startswith("modec") else "barra"
    return (f"<tr><td>{html.escape(ETIQUETAS.get(nombre, nombre))}</td><td>{v['tokens_entrada']:,}</td>"
            f"<td>{_pct(v['tasa_acierto'])}</td><td>${costo:.6f}</td>"
            f"<td style='width:30%'><div class='{clase}' style='width:{ancho:.1f}%'></div></td></tr>")


def _html_piloto(p: Mapping[str, Any]) -> str:
    ah = p.get("ahorro_relativo") or {}
    etiqueta_ahorro = "ahorro medio"
    if not ah.get("media") and p.get("ahorro_equivalente_deepseek"):
        eq = p["ahorro_equivalente_deepseek"]
        ah = {"media": eq.get("media"), "min": eq.get("min"), "corridas_validas": len(eq.get("corridas", {}))}
        etiqueta_ahorro = "ahorro equivalente a tarifa DeepSeek"
    latencias = [d.get("reduccion_latencia") for d in (p.get("corridas") or {}).values() if d.get("reduccion_latencia") is not None]
    verif = p.get("verificacion", {})
    titulo = f"{html.escape(str(p.get('proveedor')))} · {html.escape(str(p.get('modelo')))}"
    filas = []
    for c, d in (p.get("corridas") or {}).items():
        for b, t in d["brazos"].items():
            costo = next(iter(t["costos_usd"].values()), None)
            filas.append(f"<tr><td>{c}</td><td>{html.escape(ETIQUETAS.get(b, b))}</td><td>{t['llamadas_medidas']}</td>"
                         f"<td>{_pct(t['tasa_acierto'])}</td><td>{'—' if costo is None else '$' + format(Decimal(costo), '.6f')}</td>"
                         f"<td>{t['latencia_total_ms']:,.0f} ms</td></tr>")
        ahorro_c = d.get("ahorro_relativo")
        sufijo = ""
        if ahorro_c is None and p.get("ahorro_equivalente_deepseek"):
            ahorro_c = p["ahorro_equivalente_deepseek"].get("corridas", {}).get(str(c))
            sufijo = " (equivalente a tarifa DeepSeek)"
        filas.append(f"<tr><td></td><td colspan='5'>ahorro corrida {c}{sufijo}: <b>{_pct(ahorro_c)}</b> · "
                     f"reducción de latencia: <b>{_pct(d.get('reduccion_latencia'))}</b></td></tr>")
    return (f"<div class='tarjeta'><h3>{titulo}</h3><div class='kpis'>"
            f"<div class='tarjeta'><div class='cifra'>{_pct(ah.get('media'))}</div><div>{etiqueta_ahorro} "
            f"({ah.get('corridas_validas', 0)} corridas; mín {_pct(ah.get('min'))})</div></div>"
            f"<div class='tarjeta'><div class='cifra'>{_pct(min(latencias) if latencias else None)}</div>"
            f"<div>reducción mínima de latencia total por corrida</div></div>"
            f"<div class='tarjeta'><div class='cifra'>{'íntegra' if verif.get('integra') else 'revisar'}</div>"
            f"<div>cadena de evidencia ({verif.get('registros') or 0} registros; {html.escape(str(verif.get('motor_evidencia', 'pesd-nucleo')))})</div></div></div>"
            f"<table><tr><th>Corrida</th><th>Brazo</th><th>Llamadas</th><th>Acierto caché</th><th>Costo</th>"
            f"<th>Latencia total</th></tr>{''.join(filas)}</table>"
            f"<p>Procedencia: {html.escape(str(p.get('procedencia')))}."
            f"{' Detenido: ' + html.escape(str(p['detenido'])) if p.get('detenido') else ''}</p></div>")


def generar_html(simulacion: Mapping[str, Any], pilotos: Sequence[Mapping[str, Any]] = (),
                 sensibilidad: Mapping[str, Any] | None = None) -> str:
    vs = simulacion["variantes"]
    maximo = max(Decimal(v["costo_usd"]["peak"]) for v in vs.values())
    ah = simulacion["ahorro_relativo"]
    c1 = simulacion["compresion_c1"]
    filas = "".join(_fila_variante(n, v, maximo) for n, v in vs.items())
    pil = "".join(_html_piloto(p) for p in pilotos) or "<div class='tarjeta'><p>Sin pilotos ejecutados.</p></div>"
    sens = ""
    if sensibilidad:
        filas_s = "".join(
            f"<tr><td>{f['agentes']}</td><td>{f['tokens_corpus']:,}</td><td>{_pct(f['acierto_ingenua_rol'])}</td>"
            f"<td>{_pct(f['acierto_modec'])}</td><td>{_pct(f['ahorro']['deepseek_doc'])}</td>"
            f"<td>{_pct(f['ahorro']['generica_1024_128'])}</td></tr>" for f in sensibilidad["filas"])
        sens = (f"<h2>Sensibilidad (fuera de línea)</h2><div class='tarjeta'><table><tr><th>Agentes</th>"
                f"<th>Corpus (tokens)</th><th>Acierto rol arriba</th><th>Acierto MODEC-CE</th><th>Ahorro (DeepSeek)</th>"
                f"<th>Ahorro (regla 1024/128)</th></tr>{filas_s}</table><p>{html.escape(sensibilidad['procedencia'])}. "
                f"Rango: {_pct(sensibilidad['ahorro_min'])} a {_pct(sensibilidad['ahorro_max'])}.</p></div>")
    advert = "".join(f"<li>{html.escape(a)}</li>" for a in simulacion["advertencias"])
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MODEC-CE · informe</title>
<style>{_CSS}</style></head><body><main>
<h1>MODEC-CE · costo y evidencia</h1>
<p>Misma carga multiagente MODEC ({simulacion['carga']['pasos']} pasos, orquestador + {len(simulacion['carga']['agentes'])} agentes).
Las disposiciones comparten exactamente el mismo contenido: {'verificado' if simulacion['contenido_identico_entre_disposiciones'] else 'NO verificado'}.</p>
<div class="kpis">
<div class="tarjeta"><div class="cifra">{ah['modec_vs_ingenua_rol']['peak']:.0%}</div><div>ahorro estimado frente a «rol arriba», solo reordenando</div></div>
<div class="tarjeta"><div class="cifra">{ah['modec_compresion_vs_ingenua_rol']['peak']:.0%}</div><div>con historial en Super-Tokens</div></div>
<div class="tarjeta"><div class="cifra">{c1['compression_savings_ratio']:.0%}</div><div>menos tokens de historial (C.1)</div></div>
</div>
<h2>Pilotos (medición con el uso informado por el proveedor)</h2>{pil}
<h2>Simulación fuera de línea (DeepSeek, tarifa peak)</h2>
<div class="tarjeta"><table><tr><th>Disposición</th><th>Tokens de entrada</th><th>Acierto caché</th><th>Costo</th><th></th></tr>{filas}</table>
<p>Tokens: {html.escape(simulacion['procedencia_tokens'])}. Caché: {html.escape(simulacion['procedencia_cache'])}.
Costo: {html.escape(simulacion['procedencia_costo'])}.</p></div>
{sens}
<h2>Límites</h2><ul>{advert}</ul>
</main></body></html>"""
