param(
    [int]$Port = 5087,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$base = "http://127.0.0.1:$Port"
$runId = [guid]::NewGuid().ToString('N')
$work = Join-Path $PSScriptRoot "instance\proof-$runId"
$server = $null
$oldDb = $env:DB_URL
$oldConfig = $env:APP_CONFIG

function Heading([string]$title) {
    Write-Host "`n============================================================" -ForegroundColor Cyan
    Write-Host $title -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
}

function Pause-ForPhoto([string]$filename) {
    Write-Host "`nAnh minh chung: images/$filename" -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host 'Chup anh, sau do nhan Enter de tiep tuc' | Out-Null }
}

function Request([string]$method, [string]$path, [int]$expected, [string]$body = '') {
    Write-Host "`n$method $path (expected $expected)" -ForegroundColor Green
    if ($body) {
        $bodyFile = Join-Path $work 'request.json'
        [System.IO.File]::WriteAllText($bodyFile, $body, (New-Object System.Text.UTF8Encoding($false)))
        $lines = & curl.exe -i -sS -X $method "$base$path" -H 'Content-Type: application/json' --data-binary "@$bodyFile"
    } else {
        $lines = & curl.exe -i -sS -X $method "$base$path"
    }
    if ($LASTEXITCODE -ne 0) { throw "curl failed for $path" }
    $lines | ForEach-Object { Write-Host $_ }
    if (-not $lines -or $lines[0] -notmatch "^HTTP/\S+ $expected(?:\s|$)") {
        throw "Unexpected HTTP status for $method $path; expected $expected"
    }
    $jsonLine = ($lines | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1)
    if (-not $jsonLine) { throw "Missing JSON response for $path" }
    return ($jsonLine | ConvertFrom-Json)
}

try {
    if (-not (Test-Path $python)) {
        Write-Host 'Creating virtual environment and installing dependencies...' -ForegroundColor Yellow
        $runtime = Get-Command python -ErrorAction Stop
        $version = & $runtime.Source -c 'import sys; print("%s.%s" % sys.version_info[:2])'
        if ($version -notin @('3.12', '3.13')) { throw 'Use Python 3.12 or 3.13 on PATH, then rerun the script.' }
        & $runtime.Source -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv' }
        & $python -m pip install -e '.[test]'
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    }
    Heading '1. PYTEST - PRODUCT, ORDERS AND N+1'
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Pytest failed' }
    Pause-ForPhoto '01_pytest_35_passed.png'

    New-Item -ItemType Directory -Path $work -Force | Out-Null
    $env:DB_URL = 'sqlite:///' + (Join-Path $work 'proof.db').Replace('\', '/')
    $env:APP_CONFIG = 'product_api.config.DefaultConfig'
    & $python -m flask --app wsgi:app db upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port is already in use" }
    $server = Start-Process -FilePath $python -ArgumentList @('-m','flask','--app','wsgi:app','run','--host','127.0.0.1','--port',"$Port",'--no-reload') -WorkingDirectory $PSScriptRoot -RedirectStandardOutput (Join-Path $work 'server.log') -RedirectStandardError (Join-Path $work 'server.err') -WindowStyle Hidden -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($server.HasExited) { throw "API server exited; check $work\server.err (port $Port may be busy)" }
        try {
            $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
            $ready = $true
            break
        } catch {
            if ($_.Exception.Message -like 'Port *') { throw }
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { throw "API did not start on port $Port" }

    Heading '2. HEALTH PROBES'
    $health = Request 'GET' '/healthz' 200
    $readyBody = Request 'GET' '/ready' 200
    if ($health.status -ne 'ok' -or $readyBody.checks.db -ne 'ok') { throw 'Health checks failed' }
    Pause-ForPhoto '02_health_probes.png'

    Heading '3. CREATE PRODUCT 201 AND DUPLICATE SKU 409'
    $productBody = '{"sku":"PROD-01","name":"Product 01","price_cents":2500,"qty_in_stock":10}'
    $product = Request 'POST' '/api/v1/products' 201 $productBody
    if ($product.id -ne 1) { throw 'Expected product ID 1 in isolated database' }
    $conflict = Request 'POST' '/api/v1/products' 409 $productBody
    if ($conflict.code -ne 'conflict') { throw 'Expected conflict code' }
    Pause-ForPhoto '03_post_product_and_conflict.png'

    Heading '4. RESERVE STOCK 200 AND OUT OF STOCK 409'
    $reserved = Request 'POST' '/api/v1/products/1/reserve' 200 '{"qty":3}'
    if ($reserved.qty_in_stock -ne 7) { throw 'Expected remaining stock of 7' }
    $out = Request 'POST' '/api/v1/products/1/reserve' 409 '{"qty":999}'
    if ($out.code -ne 'out_of_stock') { throw 'Expected out_of_stock code' }
    Pause-ForPhoto '04_reserve_product.png'

    Heading '5. ORDER, ORDER ITEM AND EAGER LOADING'
    $order = Request 'POST' '/api/v1/orders' 201 '{"items":[{"product_id":1,"qty":1}]}'
    if ($order.id -ne 1) { throw 'Expected order ID 1 in isolated database' }
    $detail = Request 'GET' '/api/v1/orders/1' 200
    if ($detail.items.Count -ne 1 -or $detail.items[0].product.sku -ne 'PROD-01') { throw 'Missing nested order product' }
    Pause-ForPhoto '05_order_eager_loading.png'
    Write-Host "`nAll checks passed. Save the five screenshots in images/." -ForegroundColor Green
} finally {
    if ($server -and -not $server.HasExited) { & taskkill.exe /PID $server.Id /T /F | Out-Null; $server.WaitForExit() }
    $env:DB_URL = $oldDb
    $env:APP_CONFIG = $oldConfig
    if (Test-Path $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}
