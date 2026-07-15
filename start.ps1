# ============================================================
# WhatsBot -- Servidor de desarrollo
# Uso: .\start.ps1
#
# Siempre mata instancias previas (reloader + workers) antes de
# abrir una sola. Nunca mata este PowerShell ($PID).
# ============================================================

Set-Location $PSScriptRoot
$projectRoot = (Resolve-Path $PSScriptRoot).Path

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host "       WhatsBot API Server        " -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""

# 1. Migrar base de datos
Write-Host ">> Aplicando migraciones..." -ForegroundColor Cyan
python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "XX Error en migraciones. Abortando." -ForegroundColor Red
    exit 1
}
Write-Host "OK Base de datos lista" -ForegroundColor Green
Write-Host ""

# 2. Puerto desde .env
$port = 5000
if (Test-Path ".env") {
    $portLine = Select-String -Path ".env" -Pattern "^PORT=" | Select-Object -First 1
    if ($portLine) {
        $parsed = ($portLine.Line -split "=", 2)[1].Trim()
        if ($parsed -match '^\d+$') { $port = [int]$parsed }
    }
}

function Get-WhatsBotPids {
    param([int]$ListenPort, [string]$Root, [int]$SkipPid)
    $pids = New-Object 'System.Collections.Generic.HashSet[int]'

    # Dueños del puerto (cualquier estado con OwningProcess)
    try {
        Get-NetTCPConnection -LocalPort $ListenPort -ErrorAction SilentlyContinue |
            ForEach-Object {
                $op = [int]($_.OwningProcess)
                if ($op -gt 0 -and $op -ne $SkipPid) { [void]$pids.Add($op) }
            }
    } catch {}

    # python -m api.main / uvicorn de ESTE proyecto (no otros python del sistema)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            if ($cmd -notmatch 'api\.main|uvicorn') { return $false }
            # Reloader: cmdline incluye -m api.main y suele tener cwd del proyecto
            # Workers spawn_main: parent ya en $pids via taskkill /T; si no, matamos por match path
            return ($cmd -match [regex]::Escape($Root)) -or ($cmd -match 'api\.main')
        } |
        ForEach-Object {
            $op = [int]$_.ProcessId
            if ($op -gt 0 -and $op -ne $SkipPid) { [void]$pids.Add($op) }
        }

    return @($pids)
}

function Stop-WhatsBotPrevious {
    param([int]$ListenPort, [string]$Root, [int]$SkipPid)

    Write-Host ">> Cerrando instancias anteriores (solo queda la nueva)..." -ForegroundColor Cyan

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $targets = Get-WhatsBotPids -ListenPort $ListenPort -Root $Root -SkipPid $SkipPid
        if ($targets.Count -eq 0) { break }

        foreach ($procId in $targets) {
            Write-Host "   matando arbol PID $procId ..." -ForegroundColor Yellow
            # /T = reloader + worker hijos. NO matamos ParentProcessId (seria esta terminal).
            & taskkill.exe /PID $procId /T /F 2>$null | Out-Null
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }

    Start-Sleep -Seconds 1
    $still = @(Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue)
    if ($still.Count -gt 0) {
        $left = ($still | Select-Object -ExpandProperty OwningProcess -Unique) -join ","
        Write-Host "XX Puerto $ListenPort sigue ocupado (PID $left). Abortando." -ForegroundColor Red
        Write-Host "   Cerra a mano: taskkill /PID $left /T /F" -ForegroundColor Gray
        exit 1
    }

    $leftBots = Get-WhatsBotPids -ListenPort $ListenPort -Root $Root -SkipPid $SkipPid
    if ($leftBots.Count -gt 0) {
        Write-Host "XX Quedan procesos api.main: $($leftBots -join ',')" -ForegroundColor Red
        exit 1
    }

    Write-Host "OK Sin procesos viejos. Puerto $ListenPort libre." -ForegroundColor Green
    Write-Host ""
}

# $PID = este PowerShell; nunca auto-matarse
Stop-WhatsBotPrevious -ListenPort $port -Root $projectRoot -SkipPid $PID

# 3. URL publica
$apiUrl = "http://localhost:$port"
if (Test-Path ".env") {
    $line = Select-String -Path ".env" -Pattern "^API_PUBLIC_URL=" | Select-Object -First 1
    if ($line) { $apiUrl = ($line.Line -split "=", 2)[1].Trim() }
}

Write-Host ">> Iniciando UN solo servidor en $apiUrl" -ForegroundColor Cyan
Write-Host "  Docs:    $apiUrl/docs" -ForegroundColor Gray
Write-Host "  Health:  $apiUrl/health" -ForegroundColor Gray
Write-Host "  Webhook: $apiUrl/webhook" -ForegroundColor Gray
Write-Host ""
Write-Host "  Presiona Ctrl+C para detener" -ForegroundColor Gray
Write-Host ""

# 4. Unica instancia nueva
python -m api.main
