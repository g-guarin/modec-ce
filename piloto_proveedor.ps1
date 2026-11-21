#requires -Version 5.1
<#
.SYNOPSIS
    Piloto A/B real de MODEC-CE contra un proveedor de LLM. Pide la clave de forma
    protegida, la entrega solo al proceso hijo y la borra al terminar. No la escribe en disco.

.EXAMPLE
    .\piloto_proveedor.ps1 -Proveedor deepseek -Plan     # sin red: llamadas y cota de costo
    .\piloto_proveedor.ps1 -Proveedor deepseek           # piloto real: 3 corridas, 48 llamadas
    .\piloto_proveedor.ps1 -Proveedor anthropic
    .\piloto_proveedor.ps1 -Proveedor openai
    .\piloto_proveedor.ps1 -Proveedor openrouter -Modelo deepseek/deepseek-chat
#>
param(
    [ValidateSet('deepseek', 'openai', 'anthropic', 'openrouter')]
    [string]$Proveedor = 'deepseek',
    [string]$Modelo = '',
    [int]$Corridas = 3,
    [string]$Presupuesto = '0.50',
    [int]$MaxLlamadas = 60,
    [switch]$Plan
)
$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $PSScriptRoot

$variables = @{ deepseek = 'DEEPSEEK_API_KEY'; openai = 'OPENAI_API_KEY'; anthropic = 'ANTHROPIC_API_KEY'; openrouter = 'OPENROUTER_API_KEY' }
$variable = $variables[$Proveedor]
$py = 'python'
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py' }

$base = @('-B', '-m', 'modec_ce', 'piloto', '--proveedor', $Proveedor, '--corridas', "$Corridas",
          '--presupuesto', $Presupuesto, '--max-llamadas', "$MaxLlamadas")
if ($Modelo) { $base += @('--modelo', $Modelo) }

& $py @base
$codigo = $LASTEXITCODE
if ($Plan -or $codigo -ne 0) {
    if ($codigo -ne 0) { Write-Host 'El plan no cabe en los topes. No se hizo ninguna llamada.' -ForegroundColor Red }
    exit $codigo
}

Write-Host ''
Write-Host "Este piloto envía prompts SINTÉTICOS (sin datos del proyecto) a $Proveedor." -ForegroundColor Yellow
$confirmacion = Read-Host 'Para continuar escriba EJECUTAR-PILOTO'
if ($confirmacion -ne 'EJECUTAR-PILOTO') { Write-Host 'Cancelado. No se hizo ninguna llamada.'; exit 1 }

$segura = Read-Host "Clave API de $Proveedor (no se muestra)" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
try {
    Set-Item -Path "Env:$variable" -Value ([System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr))
    & $py @base --ejecutar --confirmar $confirmacion
    $codigo = $LASTEXITCODE
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    Remove-Item "Env:$variable" -ErrorAction SilentlyContinue
}
Write-Host ''
Write-Host 'Contraste el cargo en el panel de uso del proveedor con el costo derivado del informe:' -ForegroundColor Cyan
Write-Host "  $PSScriptRoot\resultados\informe.html"
exit $codigo
