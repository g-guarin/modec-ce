"""
Imprime el digest del último registro de una bitácora de evidencia.

Ese valor es lo que se sella con un ancla temporal RFC 3161: como cada registro encadena el digest
del anterior, el último resume toda la cadena. Se sella ese valor y no el archivo porque Windows
escribe CRLF y Git guarda LF, así que la copia local y la que descarga un tercero tienen bytes
distintos; el digest, en cambio, se calcula sobre el JSON canónico de cada registro y es idéntico
en ambas.

Existe como archivo, y no como una línea dentro del script de PowerShell, por una razón concreta:
PowerShell elimina las comillas dobles al pasar argumentos a un programa externo, de modo que un
`python -c "...encoding=\"utf-8\"..."` llega sin comillas y falla. Un archivo no tiene ese problema.

Uso:
    python herramientas/digest_final.py evidencia/<carpeta>
    python herramientas/digest_final.py evidencia/<carpeta>/evidencia.jsonl
    python herramientas/digest_final.py <ruta> --campos     # registros, secuencia, tipo y digest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def leer_ultimo(ruta: Path) -> dict:
    """Último registro de la bitácora. Acepta la carpeta o el propio evidencia.jsonl."""
    if ruta.is_dir():
        ruta = ruta / "evidencia.jsonl"
    lineas = [x for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lineas:
        raise ValueError(f"{ruta} no tiene registros")
    ultimo = json.loads(lineas[-1])
    return {
        "registros": len(lineas),
        "secuencia": ultimo.get("secuencia"),
        "tipo": (ultimo.get("payload") or {}).get("tipo"),
        "digest": ultimo.get("digest"),
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        d = leer_ultimo(Path(args[0]))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not isinstance(d["digest"], str) or len(d["digest"]) != 64:
        print(f"error: digest inesperado: {d['digest']!r}", file=sys.stderr)
        return 1
    if "--campos" in argv[1:]:
        print(d["registros"], d["secuencia"], d["tipo"], d["digest"])
    else:
        print(d["digest"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
