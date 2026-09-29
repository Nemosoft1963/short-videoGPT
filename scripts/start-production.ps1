$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if (!(Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Warning ".env を作成しました。外部APIを使う前にAPIキーを設定してください。"
}

docker compose config -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker compose up -d --build --remove-orphans
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$healthUrl = "http://localhost:18000/api/health"
$ready = $false
for ($attempt = 1; $attempt -le 24; $attempt++) {
  try {
    $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
    if ($response) {
      $ready = $true
      break
    }
  }
  catch {
    Start-Sleep -Seconds 5
  }
}

docker compose ps
if (-not $ready) {
  Write-Error "APIの起動確認がタイムアウトしました。docker compose logs --tail=200 api を確認してください。"
  exit 1
}

Write-Host "近道君を起動しました: http://localhost:3000" -ForegroundColor Green
Write-Host "APIドキュメント: http://localhost:18000/docs"
