# 近道君 / Short Video GPT

日本語の台本から、ナレーション・字幕・映像・BGM・ロゴを合成して短尺動画を生成するローカルWebアプリです。

## 主な機能

- React + Viteの生成UI
- FastAPI + RQ + Redisによる非同期ジョブ処理
- 縦型ショートと標準横型動画
- Runway、Google Veo、MiniMax Hailuo、MOC映像生成
- StyleBertVITS2、Qwen3-TTS、Edge TTS、gTTS音声
- ASS字幕、BGM、ロゴ、イントロ／アウトロ合成
- FFmpegによる最終レンダリング
- オプションの口パク生成サービス
- 台本プリセットと発音辞書

VOICEVOXとComfyUIは現行構成から削除されています。

## 構成

```text
frontend/          React UI
api/               FastAPI
worker/            動画生成ワーカー
lipsync_service/   オプションの口パクサービス
scripts/           補助スクリプト
docs/              仕様・運用資料
docker-compose.yml Docker構成
```

生成物、APIキー、ダウンロード済みモデル、ローカル音声環境はGitHubへ含めません。

## 必要環境

- Windows 11
- Docker Desktop
- FFmpeg（Dockerイメージ内に導入）
- NVIDIA GPU（口パクなどGPU機能を使う場合）
- 利用する外部動画APIのアカウントとAPIキー
- StyleBertVITS2またはQwen3-TTSを使う場合は別途ローカルサーバー

## セットアップ

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

UI:

```text
http://localhost:3000
```

API:

```text
http://localhost:18000/docs
```

口パク機能を使う場合:

```powershell
docker compose --profile lipsync up -d --build
```

## 音声サービス

標準設定は `.env` の `TTS_ENGINE` で選択します。

```env
TTS_ENGINE=stylebertvits2
STYLEBERTVITS2_URL=http://host.docker.internal:5000
```

Qwen3-TTSを使う場合:

```env
TTS_ENGINE=qwen3tts
QWEN3_TTS_URL=http://host.docker.internal:5005
```

ローカル音声モデル本体はリポジトリに含まれません。

## 動画生成

UIで次のモードを選択できます。

- `runway`
- `veo_lite`
- `minimax`
- `mock`（MOC、外部APIを使わない確認用映像）

APIキーは `.env` に設定してください。`.env` はGit管理対象外です。

## 出力先

```text
storage/projects/{project_id}/final/final.mp4
```

`storage/` はGit管理対象外です。完成動画とプロジェクト履歴はローカルに保存されます。

## 動作確認

```powershell
docker compose ps
Invoke-RestMethod http://localhost:18000/api/health
Invoke-RestMethod http://localhost:18000/api/diagnostics
```

## セキュリティと利用上の注意

- APIキーをソースコードやIssueへ貼り付けないでください。
- 外部動画APIは利用料金が発生する場合があります。
- 音声モデル、BGM、ロゴ、画像、生成動画の利用条件を個別に確認してください。
- このリポジトリにはライセンスファイルをまだ設定していません。
