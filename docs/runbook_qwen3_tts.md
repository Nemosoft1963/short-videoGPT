# Qwen3-TTS HTTP Bridge

This project integrates Qwen3-TTS through HTTP so the existing worker image does
not need Qwen3-TTS, torch, model weights, or Python 3.12 dependencies.

## Environment

Set these in `.env` only when you want to use Qwen3-TTS:

```env
TTS_ENGINE=qwen3tts
QWEN3_TTS_URL=http://host.docker.internal:5005
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base
QWEN3_TTS_MODE=voice_clone
QWEN3_TTS_SPEAKER=chikamichi
QWEN3_TTS_LANGUAGE=Japanese
QWEN3_TTS_INSTRUCT=
```

## Start The Bridge

Create a separate Python 3.12 environment for Qwen3-TTS:

```powershell
cd tools\qwen3tts_server
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 5005
```

The main app will call `POST /voice` and expects WAV bytes in the response.

## Chikamichi-Kun Voice Clone

Create a profile file at:

```text
tools/qwen3tts_server/voices/chikamichi.json
```

Example:

```json
{
  "speaker": "chikamichi",
  "name": "近道君",
  "mode": "voice_clone",
  "model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
  "language": "Japanese",
  "ref_audio": "C:/path/to/chikamichi_reference.wav",
  "ref_text": "Reference audio transcript goes here."
}
```

Use a clean short reference clip and the exact transcript for `ref_text`.

The repository now includes a smoke-test profile at
`tools/qwen3tts_server/voices/chikamichi.json`. It uses an existing generated
WAV only to verify the voice-clone route. Replace `ref_audio` and `ref_text`
with a clean recording of the real Chikamichi-Kun voice before production use.

## Smoke Test

```powershell
$body = @{
  text = 'テストです'
  mode = 'voice_clone'
  speaker = 'chikamichi'
  language = 'Japanese'
  model = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
} | ConvertTo-Json

Invoke-WebRequest `
  -UseBasicParsing http://localhost:5005/voice `
  -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body $body `
  -OutFile ..\..\storage\qwen3_tts_clone_smoke.wav `
  -TimeoutSec 1800
```

On this machine, the first successful smoke output was:

```text
storage/qwen3_tts_clone_smoke.wav
storage/qwen3_worker_smoke.wav
```

Current local caveat: the installed Torch wheel is CPU-only, so generation works
but may be slow. For practical production use, install a CUDA-enabled PyTorch
build in the bridge environment.
