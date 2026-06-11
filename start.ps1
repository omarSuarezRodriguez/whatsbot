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

# 2. Leer URL del .env para mostrarla
$apiUrl = "http://localhost:5000"
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

# 3. Levantar servidor
python -m api.main
