"""Informe HTML autocontenido (sin recursos externos): simulación, sensibilidad y pilotos."""
from __future__ import annotations

import html
from decimal import Decimal
from collections.abc import Mapping, Sequence
from typing import Any

from . import __version__

REPO = "https://github.com/g-guarin/modec-ce"
SITIO = "https://g-guarin.github.io/modec-ce/"
AUTOR = "Giovany Guarín Ramírez"
LICENCIA = "Apache-2.0"

# Lo que ve quien comparte el enlace antes de abrirlo. Dice para qué sirve y para quién,
# no solo qué mide: un buscador o una previsualización no leen el cuerpo de la página.
DESCRIPCION = ("Medición sellada y verificable por terceros del ahorro de costo al disponer los prompts "
               "para el caché de prefijos en orquestación multiagente sobre LLM. Para quien debe sostener "
               "una cifra de costo ante otro.")
DESCRIPCION_OG = ("No una forma nueva de ahorrar, sino una forma de demostrar cuánto se ahorró, "
                  "que un tercero puede comprobar sin instalar nada.")

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
a{color:var(--a)}
.meta{color:var(--suave);font-size:13px;margin:0 0 18px;padding-bottom:14px;border-bottom:1px solid var(--borde)}
.tesis{font-size:14.5px;line-height:1.55;margin:0 0 22px;padding:14px 16px;border-left:3px solid var(--a);background:var(--fondo);border-radius:0 6px 6px 0}
.meta b{color:var(--texto);font-weight:600}
pre{background:var(--fondo);border:1px solid var(--borde);border-radius:6px;padding:8px 10px;overflow-x:auto;font-size:12.5px;margin:8px 0 0}
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
            f"<div class='tarjeta'><div class='cifra'>{_rango_latencia(latencias)}</div>"
            f"<div>latencia por corrida: dispersión, no efecto. "
            f"{'Mejor en ' + str(sum(1 for x in latencias if x > 0)) + ' de ' + str(len(latencias)) + ' corridas' if latencias else 'sin datos'}"
            f"</div></div>"
            f"<div class='tarjeta'><div class='cifra'>{'íntegra' if verif.get('integra') else 'revisar'}</div>"
            f"<div>cadena de evidencia ({verif.get('registros') or 0} registros; {html.escape(str(verif.get('motor_evidencia', 'pesd-nucleo')))})</div></div></div>"
            f"<table><tr><th>Corrida</th><th>Brazo</th><th>Llamadas</th><th>Acierto caché</th><th>Costo</th>"
            f"<th>Latencia total</th></tr>{''.join(filas)}</table>"
            f"<p>Procedencia: {html.escape(str(p.get('procedencia')))}."
            f"{' Detenido: ' + html.escape(str(p['detenido'])) if p.get('detenido') else ''}</p>"
            f"{_cita_evidencia(p)}</div>")


def _rango_latencia(latencias: Sequence[float]) -> str:
    """El rango completo, nunca un extremo solo.

    Esta ficha mostraba el peor dato de las corridas como si fuera el resultado; un extremo no es
    la medición. Con los pilotos publicados, MODEC-CE sale mejor en la mitad de las corridas y peor
    en la otra mitad: los datos sostienen dispersión, no un efecto.
    """
    if not latencias:
        return "—"
    bajo, alto = min(latencias), max(latencias)
    if bajo == alto:
        return _pct(bajo)
    return f"{_pct(bajo)} a {_pct(alto)}"


def _cita_evidencia(p: Mapping[str, Any]) -> str:
    """Enlace a la bitácora publicada y la orden exacta para verificarla. Un número de ahorro sin
    la ruta de su evidencia obliga al lector a creer; con la ruta, puede comprobarlo."""
    carpeta = p.get("_carpeta")
    if not carpeta or not p.get("_publicada"):
        return ("<p>Bitácora no publicada en este repositorio: medición no verificable por terceros.</p>"
                if carpeta else "")
    c = html.escape(str(carpeta))
    return (f"<p>Evidencia: <a href='{REPO}/tree/main/{c}'>{c}</a> · verificable sin instalar nada:</p>"
            f"<pre>python herramientas/verificar_independiente.py {c}</pre>")


def generar_html(simulacion: Mapping[str, Any], pilotos: Sequence[Mapping[str, Any]] = (),
                 sensibilidad: Mapping[str, Any] | None = None) -> str:
    vs = simulacion["variantes"]
    maximo = max(Decimal(v["costo_usd"]["peak"]) for v in vs.values())
    ah = simulacion["ahorro_relativo"]
    c1 = simulacion["compresion_c1"]
    filas = "".join(_fila_variante(n, v, maximo) for n, v in vs.items())
    pil = "".join(_html_piloto(p) for p in pilotos) or (
        "<div class='tarjeta'><p>Este informe se generó sin ninguna bitácora de piloto a la vista. "
        f"Las bitácoras publicadas están en <a href='{REPO}/tree/main/evidencia'>evidencia/</a> del "
        "repositorio; no significa que no se hayan ejecutado pilotos.</p></div>")
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
<meta name="description" content="{html.escape(DESCRIPCION)}">
<meta name="author" content="{html.escape(AUTOR)}">
<meta property="og:title" content="MODEC-CE · costo y evidencia">
<meta property="og:description" content="{html.escape(DESCRIPCION_OG)}">
<meta property="og:type" content="website"><meta property="og:url" content="{SITIO}">
<style>{_CSS}</style></head><body><main>
<h1>MODEC-CE · costo y evidencia</h1>
<p class="meta"><b>{html.escape(AUTOR)}</b> · versión {html.escape(__version__)} · licencia {html.escape(LICENCIA)} ·
<a href="{REPO}">código fuente</a> · <a href="{REPO}/tree/main/evidencia">bitácoras de evidencia</a> ·
<a href="{REPO}/blob/main/SECURITY.md">modelo de amenaza y límites</a><br>
Informe generado por el propio programa a partir de los datos del repositorio. Las cifras de simulación son
estimaciones fuera de línea; las de los pilotos provienen del uso informado por el proveedor.</p>
<p class="tesis">Ordenar el prompt para aprovechar el caché del proveedor es práctica recomendada y no se
propone aquí como novedad. <b>Lo que MODEC-CE aporta es que la medición quede sellada y la pueda comprobar un
tercero</b>, con cada cifra marcada como estimada, medida o derivada, y con lo que no se pudo medir declarado
en vez de contado como cero. Está dirigido a quien debe sostener una cifra de costo ante otro: quien la cobra,
quien la compra, quien la audita o quien la publica. El ahorro depende tanto de la forma de la carga que un
porcentaje ajeno no sirve para decidir: lo que se ofrece es el procedimiento para medir el propio.</p>
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
