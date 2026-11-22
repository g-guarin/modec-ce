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
4. que el ahorro de cada corrida, recalculado con los costos registrados en las llamadas, coincide con `resumen.json`;
5. con `--hmac-hex`, que TODO registro trae `key_id` esperado y un HMAC válido (modo estricto: la firma no es
   opcional, porque `key_id` va dentro del cuerpo digestado y podría quitarse de todos los registros).

Límites: sin la clave HMAC de quien selló la bitácora solo se comprueba la integridad, no la autoría; la clave
es la declaración de qué firma se espera. Sin un ancla externa (p. ej. un sello de tiempo RFC 3161 sobre el
`digest` del último registro), quien reescriba la bitácora completa puede recalcular todas las huellas, y el
truncamiento de la cola no es detectable. La fecha que traen los registros la declara el equipo que ejecutó.

Uso:
    python herramientas/verificar_independiente.py evidencia/<carpeta>
    python herramientas/verificar_independiente.py evidencia/<carpeta> --hmac-hex <clave_hex> [--key-id modec-ce]
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

FORMATO = "modec-ce-cadena-minima-v1"
KEY_ID_POR_DEFECTO = "modec-ce"


def _canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _estado_ancla(carpeta: Path, digest_final: str | None) -> dict:
    """¿Hay un ancla temporal junto a esta bitácora, y corresponde a esta cadena?

    Se busca en `sello/<misma carpeta>/`. Comprobar que el ancla es de ESTA cadena no necesita
    dependencias: el digest final, en bruto, tiene que aparecer dentro de la solicitud y dentro de
    la respuesta firmada.

    Lo que esta herramienta NO hace es comprobar la firma de la autoridad, porque eso exige leer
    ASN.1 y aquí no hay más que la biblioteca estándar. Se declara en vez de darse por hecho: un
    ancla presente y no verificada no es un ancla verificada.
    """
    carpeta = carpeta.resolve()
    sello = carpeta.parent.parent / "sello" / carpeta.name
    tsq, tsr = sello / "ancla.tsq", sello / "ancla.tsr"
    sin_ancla = {"estado": "AUSENTE",
                 "limite": "SIN ANCLA EXTERNA: la reescritura total y el truncamiento de la cola no son detectables"}
    if not (tsq.is_file() and tsr.is_file()):
        return sin_ancla
    if not digest_final:
        return {"estado": "PRESENTE_SIN_CADENA_QUE_COMPARAR",
                "limite": "ANCLA PRESENTE pero la cadena no tiene digest final con el que compararla"}
    try:
        crudo = bytes.fromhex(digest_final)
    except ValueError:
        return sin_ancla
    if crudo not in tsq.read_bytes() or crudo not in tsr.read_bytes():
        return {"estado": "NO_CORRESPONDE",
                "limite": "ANCLA PRESENTE pero NO contiene el digest final de esta cadena: no es su ancla"}
    return {
        "estado": "PRESENTE_Y_CORRESPONDE_A_ESTA_CADENA",
        "limite": ("ANCLA PRESENTE en " + sello.name + ": contiene el digest final de esta cadena, "
                   "pero la FIRMA de la autoridad no se comprueba aquí. Compruébela con: "
                   "openssl ts -verify -in ancla.tsr -queryfile ancla.tsq -CAfile cacert.pem -untrusted tsa.crt"),
    }


def verificar(carpeta: Path, clave: bytes | None = None, key_id: str = KEY_ID_POR_DEFECTO) -> dict:
    registros = [json.loads(linea) for linea in
                 (carpeta / "evidencia.jsonl").read_text(encoding="utf-8").splitlines() if linea.strip()]
    fallos: list[str] = []
    anterior = None
    for i, r in enumerate(registros):
        if r.get("formato") != FORMATO:
            fallos.append(f"registro {i}: formato {r.get('formato')!r} no verificable con esta herramienta")
            continue
        cuerpo = {k: r.get(k) for k in ("formato", "secuencia", "hash_previo", "payload", "key_id")}
        cuerpo_bytes = _canonico(cuerpo)
        if hashlib.sha256(cuerpo_bytes).hexdigest() != r.get("digest"):
            fallos.append(f"registro {i}: digest no coincide (contenido alterado)")
        if r.get("secuencia") != i:
            fallos.append(f"registro {i}: secuencia {r.get('secuencia')} distinta de {i}")
        if r.get("hash_previo") != anterior:
            fallos.append(f"registro {i}: hash_previo no enlaza con el registro anterior")
        if clave is not None:                       # modo estricto: con clave, la firma no es opcional
            if not r.get("key_id"):
                fallos.append(f"registro {i}: sin HMAC; con clave se exige firma en todos los registros")
            elif r.get("key_id") != key_id:
                fallos.append(f"registro {i}: key_id {r.get('key_id')!r} distinto del esperado {key_id!r}")
            elif not hmac.compare_digest(hmac.new(clave, cuerpo_bytes, hashlib.sha256).hexdigest(),
                                         r.get("hmac") or ""):
                fallos.append(f"registro {i}: HMAC inválido")
        elif r.get("key_id"):
            fallos.append(f"registro {i}: trae HMAC y no se entregó clave para verificarlo (use --hmac-hex)")
        anterior = r.get("digest")

    costos: dict[tuple, Decimal] = defaultdict(Decimal)
    llamadas = 0
    for i, r in enumerate(registros):
        p = r.get("payload") or {}
        if p.get("tipo") != "LLAMADA":
            continue
        llamadas += 1
        try:                     # un registro malformado se reporta como fallo, no se propaga como excepción
            costos[(str(p["corrida"]), p["brazo"])] += Decimal(p["costos_usd"]["peak"])
        except (KeyError, TypeError, ArithmeticError, ValueError):
            fallos.append(f"registro {i}: LLAMADA sin corrida, brazo o costo utilizable")

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

    plan = next((r.get("payload") or {} for r in registros if (r.get("payload") or {}).get("tipo") == "PLAN"), {})
    ancla = _estado_ancla(carpeta, anterior)
    limites = [ancla["limite"]]
    limites.append("AUTENTICIDAD: HMAC verificado con la clave entregada" if clave is not None
                   else "SIN CLAVE HMAC: integridad, no autoría")
    if not plan.get("fecha_utc"):
        limites.append("SIN FECHA EN EL SELLO: esta bitácora no declara cuándo se produjo")
    if not plan.get("commit"):
        limites.append("SIN COMMIT EN EL SELLO: esta bitácora no declara con qué versión del código se produjo")

    return {
        "registros": len(registros),
        "llamadas": llamadas,
        "ancla_externa": ancla["estado"],
        "fecha_declarada_utc": plan.get("fecha_utc"),
        "version_declarada": plan.get("version_modec_ce"),
        "commit_declarado": plan.get("commit"),
        "arbol_limpio": plan.get("arbol_limpio"),
        "autenticidad": "HMAC_VERIFICADO" if clave is not None else "NO_EVALUADA (sin clave)",
        "ahorro_recalculado_por_corrida": ahorros,
        "integra": not fallos and bool(registros),
        "fallos": fallos,
        "limites": limites,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Verifica una bitácora publicada de MODEC-CE (cadena mínima).")
    p.add_argument("carpeta", help="carpeta con evidencia.jsonl y, opcionalmente, resumen.json")
    p.add_argument("--hmac-hex", default=None,
                   help="clave HMAC en hexadecimal; activa el modo estricto de autenticidad")
    p.add_argument("--key-id", default=KEY_ID_POR_DEFECTO, help=f"key_id esperado (por defecto {KEY_ID_POR_DEFECTO})")
    args = p.parse_args(argv[1:])
    try:
        clave = bytes.fromhex(args.hmac_hex.strip()) if args.hmac_hex else None
    except ValueError:
        print("--hmac-hex no es hexadecimal válido", file=sys.stderr)
        return 2
    informe = verificar(Path(args.carpeta), clave, args.key_id)
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0 if informe["integra"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
