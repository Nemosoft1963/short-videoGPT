$ErrorActionPreference = "Continue"

$nodeDir = "C:\Program Files\nodejs"
if (Test-Path $nodeDir) {
    $env:Path = "$nodeDir;$env:Path"
}

function Test-Command {
    param(
        [string]$Name,
        [string]$Command,
        [string[]]$Args = @("--version")
    )

    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "NG: command not found: $Command" -ForegroundColor Red
        return $false
    }

    Write-Host "Path: $($cmd.Source)"
    try {
        & $Command @Args
        Write-Host "OK" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "NG: command failed: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

$results = @{}
$results.Node = Test-Command -Name "Node.js" -Command "node"
$results.Npm = Test-Command -Name "npm" -Command "npm.cmd"
$results.Python = Test-Command -Name "Python" -Command "python"
$results.Pip = Test-Command -Name "pip" -Command "pip"
$results.Docker = Test-Command -Name "Docker" -Command "docker"

Write-Host ""
Write-Host "== Docker Compose ==" -ForegroundColor Cyan
try {
    docker compose version
    Write-Host "OK" -ForegroundColor Green
    $results.DockerCompose = $true
}
catch {
    Write-Host "NG: docker compose failed: $($_.Exception.Message)" -ForegroundColor Red
    $results.DockerCompose = $false
}

Write-Host ""
Write-Host "== frontend dependencies ==" -ForegroundColor Cyan
$frontendNodeModules = Join-Path $PSScriptRoot "..\frontend\node_modules"
if (Test-Path $frontendNodeModules) {
    Write-Host "OK: frontend\node_modules exists" -ForegroundColor Green
    $results.FrontendDeps = $true
}
else {
    Write-Host "NG: frontend\node_modules is missing" -ForegroundColor Yellow
    Write-Host "Run: cd C:\Users\kanto\short-videoGPT\frontend; npm.cmd install"
    $results.FrontendDeps = $false
}

Write-Host ""
Write-Host "== StyleBertVITS2 API ==" -ForegroundColor Cyan
$stylebertUrl = "http://localhost:5000"
try {
    $res = Invoke-WebRequest -Uri "$stylebertUrl/models/info" -UseBasicParsing -TimeoutSec 5
    if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 300) {
        Write-Host "OK: $stylebertUrl/models/info is reachable" -ForegroundColor Green
        $results.StyleBertVITS2 = $true
    }
    else {
        Write-Host "NG: HTTP $($res.StatusCode)" -ForegroundColor Yellow
        $results.StyleBertVITS2 = $false
    }
}
catch {
    Write-Host "Not reachable: $stylebertUrl/models/info" -ForegroundColor Yellow
    Write-Host "If you use StyleBertVITS2, start server_fastapi.py first."
    $results.StyleBertVITS2 = $false
}

Write-Host ""
Write-Host "== Summary ==" -ForegroundColor Cyan
$results.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $status = if ($_.Value) { "OK" } else { "NG" }
    $color = if ($_.Value) { "Green" } else { "Yellow" }
    Write-Host "$($_.Name): $status" -ForegroundColor $color
}

Write-Host ""
if ($results.Node -and $results.Npm -and $results.Python -and $results.Docker -and $results.DockerCompose) {
    Write-Host "Core tools are ready." -ForegroundColor Green
}
else {
    Write-Host "Some tools are missing. See docs\install_for_codex.md." -ForegroundColor Yellow
}
