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
    .\sellar_tiempo.ps1 -Documento docs\diseno-piloto-supertokens.md
#>
param(
    [string]$Bitacora = 'evidencia\piloto_deepseek_20261122_135846_5c1d7c',
    # Alternativa a -Bitacora: sella un documento de texto por su forma canonica (sin BOM y con
    # finales de linea LF), no por sus bytes. Sirve para fijar un diseno experimental antes de
    # ejecutarlo. Si se indica, -Bitacora se ignora.
    [string]$Documento = '',
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

$esDocumento = -not [string]::IsNullOrWhiteSpace($Documento)
if ($esDocumento) { $nombre = 'doc-' + [IO.Path]::GetFileNameWithoutExtension($Documento) }
else              { $nombre = Split-Path -Leaf $Bitacora }
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

# registro_sellado.txt se publica en el repositorio, asi que todo lo que se escriba en el va
# relativo a la raiz: la ruta absoluta de la maquina que sella no le sirve a quien verifica, y
# expone el nombre de usuario y la estructura de carpetas de quien ejecuta. Lo que esta fuera del
# repositorio -openssl, curl- se registra solo por su nombre de archivo.
function Rel($p) {
    $raiz = $PSScriptRoot.TrimEnd('\') + '\'
    if ("$p".StartsWith($raiz, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "$p".Substring($raiz.Length)
    }
    return (Split-Path -Leaf "$p")
}

Nota "=== Ancla temporal RFC 3161 — MODEC-CE ==="
if (-not $esDocumento) { Nota "bitacora : $Bitacora" }
Nota "destino  : $(Rel $destino)"
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
else { Nota "openssl  : $(Rel $openssl)  ($(& $openssl version 2>&1))" }

# curl.exe, no el alias curl de PowerShell, que es otro comando y no sirve aquí.
$curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
if (-not $curl) { Falla 'no se encontró curl.exe' } else { Nota "curl     : $(Rel $curl)" }

$py = 'python'
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py' }
if ($fallos -gt 0) { Nota 'Faltan herramientas. Se detiene.'; exit 1 }

# --- 2. Digest de lo que se sella ----------------------------------------------------------
if ($esDocumento) {
    $archivo = Join-Path $PSScriptRoot $Documento
    if (-not (Test-Path -LiteralPath $archivo)) { Falla "no existe $(Rel $archivo)"; exit 1 }
    $lector = Join-Path $PSScriptRoot (Join-Path 'herramientas' 'digest_documento.py')
    if (-not (Test-Path -LiteralPath $lector)) { Falla "no existe $(Rel $lector)"; exit 1 }
    $salida = (& $py -I $lector $archivo --campos 2>&1) -join ' '
    if ($LASTEXITCODE -ne 0) { Falla "no se pudo leer el documento: $salida"; exit 1 }
    $campos = $salida.Trim() -split '\s+'
    $digest = $campos[3]
    if ($digest -notmatch '^[0-9a-f]{64}$') { Falla "digest inesperado: $digest"; exit 1 }
    Nota "documento: $Documento ($($campos[0]) bytes en disco, $($campos[1]) canonicos, $($campos[2]) lineas)"
    Nota "DIGEST SELLADO: $digest"
}
else {

$jsonl = Join-Path $PSScriptRoot (Join-Path $Bitacora 'evidencia.jsonl')
if (-not (Test-Path -LiteralPath $jsonl)) { Falla "no existe $(Rel $jsonl)"; exit 1 }

# Se invoca un archivo, no `python -c "..."`: PowerShell elimina las comillas dobles al pasar
# argumentos a un programa externo, así que el código en línea llegaba con `encoding=utf-8` sin
# comillas y fallaba. Un archivo no tiene ese problema, y además le sirve a quien verifique.
$lector = Join-Path $PSScriptRoot (Join-Path 'herramientas' 'digest_final.py')
if (-not (Test-Path -LiteralPath $lector)) { Falla "no existe $(Rel $lector)"; exit 1 }
$salida = (& $py -I $lector $jsonl --campos 2>&1) -join ' '
if ($LASTEXITCODE -ne 0) { Falla "no se pudo leer la bitácora: $salida"; exit 1 }
$campos = $salida.Trim() -split '\s+'
$registros, $secuencia, $tipo, $digest = $campos[0], $campos[1], $campos[2], $campos[3]
if ($digest -notmatch '^[0-9a-f]{64}$') { Falla "digest inesperado: $digest"; exit 1 }
Nota "registros: $registros (ultimo: secuencia $secuencia, tipo $tipo)"
Nota "DIGEST SELLADO: $digest"
}

# --- 3. Solicitud --------------------------------------------------------------------------
# A partir de aquí se trabaja DENTRO de la carpeta de salida y se le pasan a openssl y curl
# nombres sueltos, nunca rutas. Motivo: la ruta de este repositorio contiene espacios y
# paréntesis, y al pasarla a un programa externo llega cortada en el primer espacio —openssl
# respondió «Could not open file ... C:\Users\Usuario\Desktop\PLATAFOR-MENS»—. Con nombres
# sueltos el problema no puede darse, venga la carpeta donde venga.
Push-Location -LiteralPath $destino
try {

$tsq = 'ancla.tsq'
$tsr = 'ancla.tsr'
& $openssl ts -query -digest $digest -sha256 -cert -out $tsq 2>&1 | ForEach-Object { Nota "  openssl: $_" }
if (-not (Test-Path -LiteralPath $tsq)) { Falla 'no se creó la solicitud'; exit 1 }
Nota "solicitud: $(Rel $destino)\$tsq ($((Get-Item $tsq).Length) bytes)"

# --- 4. Envío ------------------------------------------------------------------------------
# -o, nunca ">": la redirección de PowerShell pasa la salida por un filtro de texto y corrompe
# un archivo binario como este.
& $curl -sS -H 'Content-Type: application/timestamp-query' --data-binary "@$tsq" $Tsa -o $tsr 2>&1 |
    ForEach-Object { Nota "  curl: $_" }
if (-not (Test-Path -LiteralPath $tsr)) { Falla 'no se recibió respuesta'; exit 1 }
$bytes = (Get-Item $tsr).Length
Nota "respuesta: $(Rel $destino)\$tsr ($bytes bytes)"
if ($bytes -lt 1000) {
    Falla "la respuesta es demasiado pequeña; probablemente sea un mensaje de error en texto:"
    Nota (Get-Content -LiteralPath $tsr -Raw -ErrorAction SilentlyContinue)
    exit 1
}

# --- 5. Certificados -----------------------------------------------------------------------
$certTsa = 'tsa.crt'
$certCa = 'cacert.pem'
& $curl -sS $UrlCertTsa -o $certTsa 2>&1 | ForEach-Object { Nota "  curl: $_" }
& $curl -sS $UrlCertCa -o $certCa 2>&1 | ForEach-Object { Nota "  curl: $_" }
foreach ($c in @($certTsa, $certCa)) {
    if (-not (Test-Path -LiteralPath $c)) { Falla "no se descargó $c"; exit 1 }
    Nota "certificado: $(Rel $destino)\$c ($((Get-Item $c).Length) bytes) sha256=$((Get-FileHash $c -Algorithm SHA256).Hash.ToLower())"
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

} finally { Pop-Location }

# --- 7. LEEME para quien verifique ---------------------------------------------------------
# Dos plantillas, no una: en el modo -Documento no hay cadena, ni secuencia, ni tipo, y la
# comprobacion del valor sellado se hace con digest_documento.py sobre el documento. Reutilizar
# la plantilla de bitacora deja un LEEME.txt que nombra una bitacora ajena y propone un comando
# que imprime otro digest, de modo que quien verifique concluye que el sello no corresponde.
if ($esDocumento) {
$leeme = @"
Ancla temporal RFC 3161 del documento $Documento

Valor sellado: digest SHA-256 de la FORMA CANÓNICA del documento, es decir del archivo sin BOM y
con finales de línea LF:

    $digest

Autoridad : FreeTSA ($Tsa)
Sellado el: $instante

QUÉ ACREDITA: que un documento con ese contenido exacto existía a más tardar en ese instante. NO
acredita autoría, NO acredita que el contenido sea cierto, y NO acredita ninguna fecha escrita
dentro del documento.

POR QUÉ LA FORMA CANÓNICA Y NO LOS BYTES: la copia de trabajo en Windows lleva CRLF y la que
descarga un tercero desde GitHub lleva LF. Un sello sobre los bytes valdría para una sola de las
dos. El digest canónico es el mismo en ambas.

Los certificados tsa.crt y cacert.pem se publican junto al sello a propósito: si FreeTSA dejara de
estar disponible, quien quiera verificar los necesitaría. Son certificados públicos, no secretos.
Sus huellas SHA-256 están en registro_sellado.txt, junto a la fecha en que se descargaron.

CÓMO VERIFICARLO (necesita openssl):

    openssl ts -verify -in ancla.tsr -queryfile ancla.tsq -CAfile cacert.pem -untrusted tsa.crt

Debe responder exactamente: Verification: OK

Y para comprobar que el valor sellado es el de este documento, y no el de otro, desde la raíz del
repositorio:

    python herramientas/digest_documento.py $($Documento -replace '\\','/')
    openssl ts -query -in sello/$nombre/ancla.tsq -text

El valor que imprime el primero debe coincidir con el bloque "Message data" de la salida del
segundo. openssl lo muestra como volcado hexadecimal repartido en varias líneas y con espacios,
así que hay que compararlo quitando los espacios, no línea a línea.
"@
}
else {
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

Y para comprobar que el valor sellado es el de esta bitácora, y no el de otra, desde la raíz del
repositorio:

    python herramientas/digest_final.py $($Bitacora -replace '\\','/')
    openssl ts -query -in sello/$nombre/ancla.tsq -text

El valor que imprime el primero debe coincidir con el bloque "Message data" de la salida del
segundo. openssl lo muestra como volcado hexadecimal repartido en varias líneas y con espacios,
así que hay que compararlo quitando los espacios, no línea a línea.
"@
}
Set-Content -LiteralPath (Join-Path $destino 'LEEME.txt') -Value $leeme -Encoding utf8

Nota ''
Nota "=== TERMINADO SIN ERRORES ==="
Nota "Archivos en: $(Rel $destino)"
Get-ChildItem -LiteralPath $destino | ForEach-Object { Nota ("  " + $_.Name + "  " + $_.Length + " bytes") }
Nota ''
Nota 'Nada se ha publicado todavía. Revise el contenido antes de hacer commit.'
exit 0
