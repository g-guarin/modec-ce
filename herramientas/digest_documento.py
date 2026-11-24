"""
Imprime el digest SHA-256 de un documento de texto en su forma canónica.

Sirve para sellar con un ancla temporal RFC 3161 algo que no es una bitácora: un diseño
experimental, una especificación, un informe. Acredita que ese documento, con ese contenido
exacto, existía a más tardar en el instante que firma la autoridad.

Se digesta la forma canónica y no los bytes del archivo por la misma razón que en
`digest_final.py`: Windows escribe CRLF y Git guarda LF, así que la copia local y la que descarga
un tercero desde GitHub tienen bytes distintos y un sello sobre los bytes valdría para una sola de
las dos.

Forma canónica, definida para que cualquiera pueda reproducirla:

    1. Se leen los bytes del archivo.
    2. Si empiezan por la marca BOM de UTF-8 (EF BB BF), se descarta.
    3. Se decodifica como UTF-8.
    4. Todo CRLF y todo CR suelto pasan a LF.
    5. Se vuelve a codificar como UTF-8 y se calcula SHA-256.

Equivalente en una línea, para comprobarlo sin este archivo:

    python -c "import hashlib,sys;d=open(sys.argv[1],'rb').read().removeprefix(b'\\xef\\xbb\\xbf');\
print(hashlib.sha256(d.replace(b'\\r\\n',b'\\n').replace(b'\\r',b'\\n')).hexdigest())" RUTA

Lo que NO acredita: autoría, veracidad del contenido, ni que el documento no se haya modificado
después. Solo que esa versión existía en ese instante.

Uso:
    python herramientas/digest_documento.py docs/diseno-piloto-supertokens.md
    python herramientas/digest_documento.py RUTA --campos    # bytes, lineas y digest
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"


def canonico(crudo: bytes) -> bytes:
    """Bytes del documento en la forma que se digesta: sin BOM y con finales de línea LF."""
    return crudo.removeprefix(BOM).replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def digest_documento(ruta: Path) -> dict:
    crudo = ruta.read_bytes()
    canon = canonico(crudo)
    return {
        "bytes_archivo": len(crudo),
        "bytes_canonicos": len(canon),
        "lineas": canon.count(b"\n"),
        "digest": hashlib.sha256(canon).hexdigest(),
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    ruta = Path(args[0])
    if ruta.is_dir():
        print(f"error: {ruta} es una carpeta; se espera un archivo", file=sys.stderr)
        return 1
    try:
        d = digest_documento(ruta)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if d["bytes_canonicos"] == 0:
        print(f"error: {ruta} está vacío", file=sys.stderr)
        return 1
    if "--campos" in argv[1:]:
        print(d["bytes_archivo"], d["bytes_canonicos"], d["lineas"], d["digest"])
    else:
        print(d["digest"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
