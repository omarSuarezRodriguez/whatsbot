# ============================================================
# WhatsBot — Servidor de desarrollo
# Uso: .\start.ps1
# ============================================================

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "╔══════════════════════════════════╗" -ForegroundColor Green
Write-Host "║       WhatsBot API Server        ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# 1. Migrar base de datos
Write-Host "▶ Aplicando migraciones..." -ForegroundColor Cyan
python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Error en migraciones. Abortando." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Base de datos lista" -ForegroundColor Green
Write-Host ""

# 2. Matar procesos viejos en el mismo puerto (evita 2 api.main → From/env mezclados)
$port = 5000
if (Test-Path ".env") {
    $portLine = Select-String -Path ".env" -Pattern "^PORT=" | Select-Object -First 1
    if ($portLine) {
        $parsed = ($portLine.Line -split "=", 2)[1].Trim()
        if ($parsed -match '^\d+$') { $port = [int]$parsed }
    }
}
$owners = @()
try {
    $owners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
} catch {}
foreach ($procId in $owners) {
    if (-not $procId -or $procId -eq 0) { continue }
    Write-Host "▶ Liberando puerto $port (PID $procId)..." -ForegroundColor Yellow
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
# Reloader/workers huérfanos de arranques previos
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'api\.main' } |
    ForEach-Object {
        Write-Host "▶ Matando api.main huérfano PID $($_.ProcessId)..." -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Seconds 1

# 3. Leer URL del .env para mostrarla
$apiUrl = "http://localhost:$port"
if (Test-Path ".env") {
    $line = Select-String -Path ".env" -Pattern "^API_PUBLIC_URL=" | Select-Object -First 1
    if ($line) { $apiUrl = ($line.Line -split "=", 2)[1].Trim() }
}

Write-Host "▶ Iniciando servidor en $apiUrl" -ForegroundColor Cyan
Write-Host "  Docs:    $apiUrl/docs" -ForegroundColor Gray
Write-Host "  Health:  $apiUrl/health" -ForegroundColor Gray
Write-Host "  Webhook: $apiUrl/webhook" -ForegroundColor Gray
Write-Host ""
Write-Host "  Presiona Ctrl+C para detener" -ForegroundColor Gray
Write-Host ""

# 4. Levantar servidor
python -m api.main
