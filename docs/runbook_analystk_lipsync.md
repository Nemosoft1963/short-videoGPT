# AnalystK high precision lip-sync

分析官Kが話すシーンだけ、外部HTTPリップシンクサービスで生成した動画に差し替える。
既存のTTS/映像生成に失敗を波及させないため、HTTP生成に失敗した場合は従来の `talker_AnalystK` 表示をそのまま使う。

## Environment

`.env`:

```env
LIPSYNC_ENABLED=true
LIPSYNC_URL=http://lipsync:7860
LIPSYNC_ENDPOINT=/generate
LIPSYNC_TIMEOUT_SECONDS=1800
LIPSYNC_ANALYSTK_SOURCE=
LIPSYNC_ANALYSTK_SOURCE_MODE=image
LIPSYNC_ANALYSTK_IMAGE_SOURCE=
LIPSYNC_ANALYSTK_VIDEO_SOURCE=
LIPSYNC_PROVIDER=command
LIPSYNC_COMMAND_TEMPLATE=
WAV2LIP_DIR=/models/Wav2Lip
WAV2LIP_CHECKPOINT=/models/Wav2Lip/checkpoints/wav2lip_gan.pth
```

`LIPSYNC_ANALYSTK_SOURCE` は任意。指定しない場合は、そのシーンの既存動画クリップを source として送る。
高精度にする場合は、分析官Kの正面顔画像または短い正面顔動画を `/storage/assets/lipsync/analystk.png` などに置き、以下のように指定する。

```env
LIPSYNC_ANALYSTK_SOURCE=/storage/assets/lipsync/analystk.png
```

静止画と動画を切り替える場合:

```env
LIPSYNC_ANALYSTK_SOURCE_MODE=image
LIPSYNC_ANALYSTK_IMAGE_SOURCE=/storage/assets/analystk_lipsync_source.png
LIPSYNC_ANALYSTK_VIDEO_SOURCE=/storage/assets/analystk_lipsync_source.mp4
```

`LIPSYNC_ANALYSTK_SOURCE_MODE=video` で動画素材、`image` で静止画素材を優先する。`auto` は動画、画像、旧 `LIPSYNC_ANALYSTK_SOURCE` の順で存在する素材を使う。

## Start service

```powershell
docker compose --profile lipsync up -d --build lipsync
```

Health check:

```powershell
Invoke-RestMethod http://localhost:7860/health
```

The service is implemented in `lipsync_service/`.
By default it is a provider wrapper. It does not bundle large model weights.

## HTTP contract

近道君 worker は以下の multipart POST を送る。

```http
POST {LIPSYNC_URL}{LIPSYNC_ENDPOINT}
Content-Type: multipart/form-data

source: image/video file
audio: wav file
speaker: AnalystK
width: 1080
height: 1920
fps: 30
duration: scene duration seconds
mode: high_precision
```

レスポンスは次のどれかを受け付ける。

- `video/mp4` などの動画バイナリ
- JSON `{ "path": "/storage/..." }`
- JSON `{ "output_path": "/storage/..." }`
- JSON `{ "video_url": "http://..." }`
- JSON `{ "download_url": "http://..." }`

## Pipeline

1. 通常通りシーン動画を生成する
2. TTS音声を生成し、尺調整と音量正規化を行う
3. `speaker == AnalystK` のシーンだけリップシンクHTTPへ送る
4. 成功したら `scene_XX_lipsync.mp4` に差し替える
5. 失敗したら既存シーンクリップを維持する
6. 字幕、BGM、ロゴ、最終結合は従来通り処理する

## Motoko fullscreen with graphic overlay

Use this script tag when AnalystK/Motoko should be the full-screen talking video and the local graphic layer should be placed on top:

```text
映像：[motoko:fullscreen] [overlay:graphic:*] [graphic:bar_chart] 項目A:10 項目B:25
AnalystK：ここでは、数字の差を見せます。
```

`[motoko:fullscreen]` overrides only that scene to full-screen lip-sync. `[overlay:graphic:*]` changes the following `[graphic:*]` in the same scene from the base video into a foreground overlay. If no graphic tag is provided, the scene behaves as a normal full-screen lip-sync scene.

## Recommended providers

- Wav2Lip: 口同期が安定。顔の動きは少なめ
- SadTalker: 顔全体の動きが出る。長尺は確認が必要
- MuseTalk: 品質と速度のバランスが良い。GPU推奨

## Provider setup

### Generic command provider

Set `LIPSYNC_PROVIDER=command` and write a command template that outputs `{output}`.

Example:

```env
LIPSYNC_COMMAND_TEMPLATE=python /models/MuseTalk/infer.py --source {source} --audio {audio} --result {output}
```

Available variables:

- `{source}`
- `{audio}`
- `{output}`
- `{width}`
- `{height}`
- `{fps}`
- `{duration}`

### Wav2Lip provider

Place Wav2Lip under `storage/lipsync_models/Wav2Lip`.

Expected files:

```text
storage/lipsync_models/Wav2Lip/inference.py
storage/lipsync_models/Wav2Lip/checkpoints/wav2lip_gan.pth
```

Then set:

```env
LIPSYNC_PROVIDER=wav2lip
WAV2LIP_DIR=/models/Wav2Lip
WAV2LIP_CHECKPOINT=/models/Wav2Lip/checkpoints/wav2lip_gan.pth
```

The compose service mounts `./storage/lipsync_models` to `/models`.
