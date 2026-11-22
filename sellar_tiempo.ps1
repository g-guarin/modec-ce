#requires -Version 5.1
<#
.SYNOPSIS
    Ancla temporal RFC 3161 sobre una bitácora de evidencia de MODEC-CE.

.DESCRIPTION
    Sella el digest del ÚLTIMO registro de la cadena, no el archivo. Razón concreta: Windows
    escribe los archivos con CRLF y Git los guarda con LF, así que la copia local y la que descarga
    un tercero desde GitHub tienen bytes distintos. Un sello sobre el archivo valdría para una sola
    de las dos. El digest no tiene ese problema: se calcula sobre el JSON canónico de cada
    registro, no sobre los bytes del archivo, y es idéntico en ambas copias. Además, como cada
    registro encadena el digest del anterior, el último resume toda la cadena.

    Qué acredita el resultado: que ese digest, y por tanto la cadena que lo produce, existía a más
    tardar en el instante que firma la autoridad. NO acredita autoría, NO acredita que el contenido
    sea cierto, y NO acredita la fecha declarada dentro de la bitácora.

    Todo lo que hace queda escrito en registro_sellado.txt, dentro de la carpeta de salida.

.EXAMPLE
    .\sellar_tiempo.ps1
    .\sellar_tiempo.ps1 -Bitacora evidencia\piloto_deepseek_20261121
#>
param(
    [string]$Bitacora = 'evidencia\piloto_deepseek_20261122_135846_5c1d7c',
    [string]$Tsa = 'https://freetsa.org/tsr',
    [string]$UrlCertTsa = 'https://freetsa.org/files/tsa.crt',
    [string]$UrlCertCa = 'https://freetsa.org/files/cacert.pem',
    # Huella publicada por FreeTSA en su página al 2026-11-22. Si no coincide, el script avisa y
    # NO continúa: o el certificado se actualizó (y hay que tomar la huella nueva de la página
    # oficial) o algo interceptó la descarga. Ante la duda, se detiene.
    [string]$HuellaCertTsa = '8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467',
    [switch]$OmitirHuella
)

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

$nombre = Split-Path -Leaf $Bitacora
$destino = Join-Path $PSScriptRoot (Join-Path 'sello' $nombre)
New-Item -ItemType Directory -Force -Path $destino | Out-Null
$registro = Join-Path $destino 'registro_sellado.txt'
Remove-Item -LiteralPath $registro -ErrorAction SilentlyContinue

$fallos = 0
function Nota($m) {
    $linea = "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK')  $m"
    Write-Host $linea
    Add-Content -LiteralPath $registro -Value $linea -Encoding utf8
}
function Falla($m) { $script:fallos++; Nota "ERROR: $m" }

Nota "=== Ancla temporal RFC 3161 — MODEC-CE ==="
Nota "bitacora : $Bitacora"
Nota "destino  : $destino"
Nota "autoridad: $Tsa"

# --- 1. Herramientas -----------------------------------------------------------------------
$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) {
    foreach ($c in @("$env:ProgramFiles\Git\usr\bin\openssl.exe",
                     "${env:ProgramFiles(x86)}\Git\usr\bin\openssl.exe",
                     "$env:LOCALAPPDATA\Programs\Git\usr\bin\openssl.exe")) {
        if (Test-Path -LiteralPath $c) { $openssl = $c; break }
    }
}
if (-not $openssl) { Falla 'no se encontró openssl (viene con Git para Windows)'; }
else { Nota "openssl  : $openssl  ($(& $openssl version 2>&1))" }

# curl.exe, no el alias curl de PowerShell, que es otro comando y no sirve aquí.
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
if (-not $curl) { Falla 'no se encontró curl.exe' } else { Nota "curl     : $curl" }

$py = 'python'
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py' }
if ($fallos -gt 0) { Nota 'Faltan herramientas. Se detiene.'; exit 1 }

# --- 2. Digest del último registro ---------------------------------------------------------
$jsonl = Join-Path $PSScriptRoot (Join-Path $Bitacora 'evidencia.jsonl')
if (-not (Test-Path -LiteralPath $jsonl)) { Falla "no existe $jsonl"; exit 1 }

$lector = @'
import json, sys
lineas = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
ultimo = json.loads(lineas[-1])
print(len(lineas), ultimo["secuencia"], (ultimo.get("payload") or {}).get("tipo"), ultimo["digest"])
'@
$salida = (& $py -I -c $lector $jsonl 2>&1) -join ' '
if ($LASTEXITCODE -ne 0) { Falla "no se pudo leer la bitácora: $salida"; exit 1 }
$campos = $salida.Trim() -split '\s+'
$registros, $secuencia, $tipo, $digest = $campos[0], $campos[1], $campos[2], $campos[3]
if ($digest -notmatch '^[0-9a-f]{64}$') { Falla "digest inesperado: $digest"; exit 1 }
Nota "registros: $registros (ultimo: secuencia $secuencia, tipo $tipo)"
Nota "DIGEST SELLADO: $digest"

# --- 3. Solicitud --------------------------------------------------------------------------
$tsq = Join-Path $destino 'ancla.tsq'
$tsr = Join-Path $destino 'ancla.tsr'
& $openssl ts -query -digest $digest -sha256 -cert -out $tsq 2>&1 | ForEach-Object { Nota "  openssl: $_" }
if (-not (Test-Path -LiteralPath $tsq)) { Falla 'no se creó la solicitud'; exit 1 }
Nota "solicitud: $tsq ($((Get-Item $tsq).Length) bytes)"

# --- 4. Envío ------------------------------------------------------------------------------
# -o, nunca ">": la redirección de PowerShell pasa la salida por un filtro de texto y corrompe
# un archivo binario como este.
& $curl -sS -H 'Content-Type: application/timestamp-query' --data-binary "@$tsq" $Tsa -o $tsr 2>&1 |
    ForEach-Object { Nota "  curl: $_" }
if (-not (Test-Path -LiteralPath $tsr)) { Falla 'no se recibió respuesta'; exit 1 }
$bytes = (Get-Item $tsr).Length
Nota "respuesta: $tsr ($bytes bytes)"
if ($bytes -lt 1000) {
    Falla "la respuesta es demasiado pequeña; probablemente sea un mensaje de error en texto:"
    Nota (Get-Content -LiteralPath $tsr -Raw -ErrorAction SilentlyContinue)
    exit 1
}

# --- 5. Certificados -----------------------------------------------------------------------
$certTsa = Join-Path $destino 'tsa.crt'
$certCa = Join-Path $destino 'cacert.pem'
& $curl -sS $UrlCertTsa -o $certTsa 2>&1 | ForEach-Object { Nota "  curl: $_" }
& $curl -sS $UrlCertCa -o $certCa 2>&1 | ForEach-Object { Nota "  curl: $_" }
foreach ($c in @($certTsa, $certCa)) {
    if (-not (Test-Path -LiteralPath $c)) { Falla "no se descargó $c"; exit 1 }
    Nota "certificado: $c ($((Get-Item $c).Length) bytes) sha256=$((Get-FileHash $c -Algorithm SHA256).Hash.ToLower())"
}
$huella = (Get-FileHash $certTsa -Algorithm SHA256).Hash.ToLower()
if ($huella -ne $HuellaCertTsa.ToLower()) {
    Falla "la huella de tsa.crt NO coincide con la esperada."
    Nota "  esperada: $($HuellaCertTsa.ToLower())"
    Nota "  obtenida: $huella"
    Nota '  O el certificado se actualizó (tome la huella nueva de la página oficial de FreeTSA)'
    Nota '  o la descarga fue interceptada. Ante la duda, no se continúa.'
    if (-not $OmitirHuella) { Nota 'Use -OmitirHuella solo si confirmó el cambio en la página oficial.'; exit 1 }
    Nota '  -OmitirHuella activo: se continúa bajo responsabilidad del operador.'
}

# --- 6. Verificación -----------------------------------------------------------------------
$verif = (& $openssl ts -verify -in $tsr -queryfile $tsq -CAfile $certCa -untrusted $certTsa 2>&1) -join "`n"
Nota "verificacion: $verif"
if ($verif -notmatch 'Verification: OK') { Falla 'la verificación NO dio OK'; exit 1 }

$detalle = (& $openssl ts -reply -in $tsr -text 2>&1) -join "`n"
Add-Content -LiteralPath $registro -Value "`n--- openssl ts -reply -text ---`n$detalle" -Encoding utf8
$instante = ([regex]::Match($detalle, 'Time stamp:\s*(.+)')).Groups[1].Value.Trim()
Nota "INSTANTE ACREDITADO: $instante"

# --- 7. LEEME para quien verifique ---------------------------------------------------------
$leeme = @"
Ancla temporal RFC 3161 de la bitácora $Bitacora

Valor sellado: digest SHA-256 del último registro de la cadena (secuencia $secuencia, tipo $tipo),
que encadena a todos los anteriores:

    $digest

Autoridad : FreeTSA ($Tsa)
Sellado el: $instante

QUÉ ACREDITA: que ese digest, y por tanto la cadena completa que lo produce, existía a más tardar
en ese instante. NO acredita autoría, NO acredita que el contenido sea cierto, y NO acredita la
fecha declarada dentro de la bitácora, que la pone el equipo que ejecutó el piloto.

Los certificados tsa.crt y cacert.pem se publican junto al sello a propósito: si FreeTSA dejara de
estar disponible, quien quiera verificar los necesitaría. Son certificados públicos, no secretos.
Sus huellas SHA-256 están en registro_sellado.txt, junto a la fecha en que se descargaron.

CÓMO VERIFICARLO (necesita openssl):

    openssl ts -verify -in ancla.tsr -queryfile ancla.tsq -CAfile cacert.pem -untrusted tsa.crt

Debe responder exactamente: Verification: OK

Y para comprobar que el valor sellado es el de esta bitácora, y no el de otra:

    python -I -c "import json;ls=[l for l in open('../../$($Bitacora -replace '\\','/')/evidencia.jsonl',encoding='utf-8').read().splitlines() if l.strip()];print(json.loads(ls[-1])['digest'])"
    openssl ts -query -in ancla.tsq -text

El valor que imprime el primero debe coincidir con el bloque "Message data" de la salida del
segundo. openssl lo muestra como volcado hexadecimal repartido en varias líneas y con espacios,
así que hay que compararlo quitando los espacios, no línea a línea.
"@
Set-Content -LiteralPath (Join-Path $destino 'LEEME.txt') -Value $leeme -Encoding utf8

Nota ''
Nota "=== TERMINADO SIN ERRORES ==="
Nota "Archivos en: $destino"
Get-ChildItem -LiteralPath $destino | ForEach-Object { Nota ("  " + $_.Name + "  " + $_.Length + " bytes") }
Nota ''
Nota 'Nada se ha publicado todavía. Revise el contenido antes de hacer commit.'
exit 0
