if (!(Test-Path .env)) {
  Copy-Item .env.example .env
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
Start-Process "http://localhost:3000"
