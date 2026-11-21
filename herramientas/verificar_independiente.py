"""Verificación independiente de una bitácora publicada de MODEC-CE (cadena mínima).

Solo usa la biblioteca estándar de Python. No necesita el paquete modec_ce ni ningún otro
componente: se puede leer y ejecutar sola.

Formato que verifica (`modec-ce-cadena-minima-v1`), una línea JSON por registro:
    formato, secuencia, hash_previo, payload, key_id, hmac, digest
donde `digest` es SHA-256 del JSON canónico (claves ordenadas, sin espacios, UTF-8) de
{formato, secuencia, hash_previo, payload, key_id}.

Comprueba:
1. que cada `digest` coincide con el contenido del registro;
2. que `secuencia` es 0, 1, 2, … sin saltos;
3. que cada `hash_previo` es el `digest` del registro anterior;
4. que el ahorro de cada corrida, recalculado desde las llamadas, coincide con `resumen.json`.

Límites: sin la clave HMAC del titular solo se comprueba la integridad, no la autoría. Sin
un ancla externa, quien reescriba la bitácora completa puede recalcular todas las huellas.

Uso:
    python herramientas/verificar_independiente.py evidencia/<carpeta>
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

FORMATO = "modec-ce-cadena-minima-v1"


def _canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def verificar(carpeta: Path) -> dict:
    registros = [json.loads(linea) for linea in
                 (carpeta / "evidencia.jsonl").read_text(encoding="utf-8").splitlines() if linea.strip()]
    fallos: list[str] = []
    anterior = None
    for i, r in enumerate(registros):
        if r.get("formato") != FORMATO:
            fallos.append(f"registro {i}: formato {r.get('formato')!r} no verificable con esta herramienta")
            continue
        cuerpo = {k: r.get(k) for k in ("formato", "secuencia", "hash_previo", "payload", "key_id")}
        if hashlib.sha256(_canonico(cuerpo)).hexdigest() != r.get("digest"):
            fallos.append(f"registro {i}: digest no coincide (contenido alterado)")
        if r.get("secuencia") != i:
            fallos.append(f"registro {i}: secuencia {r.get('secuencia')} distinta de {i}")
        if r.get("hash_previo") != anterior:
            fallos.append(f"registro {i}: hash_previo no enlaza con el registro anterior")
        anterior = r.get("digest")

    costos: dict[tuple, Decimal] = defaultdict(Decimal)
    llamadas = 0
    for r in registros:
        p = r.get("payload") or {}
        if p.get("tipo") == "LLAMADA":
            llamadas += 1
            costos[(str(p["corrida"]), p["brazo"])] += Decimal(p["costos_usd"]["peak"])

    resumen_path = carpeta / "resumen.json"
    ahorros = {}
    if resumen_path.exists():
        resumen = json.loads(resumen_path.read_text(encoding="utf-8"))
        for corrida, datos in resumen.get("corridas", {}).items():
            base, modec = costos[(corrida, "ingenua_rol")], costos[(corrida, "modec")]
            if not base:
                fallos.append(f"corrida {corrida}: sin llamadas del brazo de referencia")
                continue
            ahorro = float(1 - modec / base)
            ahorros[corrida] = round(ahorro, 4)
            if abs(ahorro - datos["ahorro_relativo"]) > 1e-4:
                fallos.append(f"corrida {corrida}: ahorro recalculado {ahorro:.4f} "
                              f"distinto del resumen {datos['ahorro_relativo']}")

    return {
        "registros": len(registros),
        "llamadas": llamadas,
        "ahorro_recalculado_por_corrida": ahorros,
        "integra": not fallos and bool(registros),
        "fallos": fallos,
        "limites": ["SIN CLAVE HMAC: integridad, no autoría", "SIN ANCLA EXTERNA: la reescritura total no es detectable"],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    informe = verificar(Path(argv[1]))
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0 if informe["integra"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
