$ErrorActionPreference = "Continue"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

docker compose ps -a

try {
  $health = Invoke-RestMethod -Uri "http://localhost:18000/api/health" -TimeoutSec 5
  Write-Host "API: OK" -ForegroundColor Green
  $health | ConvertTo-Json -Depth 5
}
catch {
  Write-Host "API: stopped or not ready" -ForegroundColor Yellow
}

try {
  $queueLength = docker compose exec -T redis redis-cli llen rq:queue:video 2>$null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "Queue: $queueLength"
  }
  else {
    Write-Host "Queue: unavailable" -ForegroundColor Yellow
  }
}
catch {
  Write-Host "Queue: unavailable" -ForegroundColor Yellow
}
