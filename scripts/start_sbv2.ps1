$ErrorActionPreference = "Stop"

$sbv2Dir = "C:\Users\kanto\short-videoGPT\tools\sbv2\sbv2\Style-Bert-VITS2"
$python = Join-Path $sbv2Dir "venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "StyleBertVITS2 venv python not found: $python"
}

Push-Location $sbv2Dir
try {
    Write-Host "Starting StyleBertVITS2 FastAPI on http://localhost:5000"
    & $python server_fastapi.py --dir model_assets
}
finally {
    Pop-Location
}

