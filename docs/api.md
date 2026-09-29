# APIリファレンス

ベースURLは `http://localhost:18000` です。対話形式の完全なスキーマは、起動後に `http://localhost:18000/docs` で確認できます。

## 稼働・診断

| メソッド | パス | 内容 |
|---|---|---|
| `GET` | `/api/health` | APIの稼働確認 |
| `GET` | `/api/diagnostics` | Redis、TTS、動画生成サービス等の接続診断 |
| `GET` | `/api/voices` | 現在のTTSエンジンで利用できる話者一覧 |

```powershell
Invoke-RestMethod http://localhost:18000/api/health
Invoke-RestMethod http://localhost:18000/api/diagnostics
```

## プロジェクトを作成する

```http
POST /api/projects
Content-Type: application/json
```

最小構成の例：

```json
{
  "title": "動作確認",
  "script": "映像：[graphic:title] 動作確認\nナレーション：生成処理を確認します。\n字幕：動作確認。",
  "format": "short_vertical",
  "duration": 15,
  "model": "mock",
  "tts_engine": "gtts",
  "subtitle": true,
  "bgm": false
}
```

レスポンス例：

```json
{
  "project_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "queued",
  "status_url": "/api/projects/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/status",
  "download_url": "/api/projects/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/download"
}
```

### 主な生成パラメーター

| 項目 | 値・範囲 | 内容 |
|---|---|---|
| `format` | `short_vertical` / `standard_landscape` | 縦型または横型 |
| `duration` | 15～600 | 目標秒数 |
| `model` | `mock` / `runway` / `luma` / `veo_lite` / `minimax` | 映像生成方式 |
| `tts_engine` | `gtts` / `edge` / `stylebertvits2` / `qwen3tts` | 音声合成方式 |
| `short_timing_mode` | `fixed_44` / `fixed_57` / `script` | ショートの尺制御 |
| `standard_timing_mode` | `duration_min` / `script_unbounded` | 横型動画の尺制御 |
| `subtitle` | boolean | 字幕の有無 |
| `subtitle_font_size` | 36～120 | 字幕サイズ |
| `subtitle_wrap_chars` | 8～28 | 1行あたりの目安文字数 |
| `subtitle_max_lines` | 1～5 | 同時表示する最大行数 |
| `subtitle_position_from_bottom_pct` | 6～55 | 画面下からの字幕位置（%） |
| `bgm` | boolean | BGM合成 |
| `bgm_auto` | boolean | BGM自動選択 |
| `bgm_filename` | string | 登録済みBGM |
| `logo_filename` | string | 登録済みロゴ |
| `intro_video_filename` | string | 冒頭に連結する動画 |
| `outro_video_filename` | string | 末尾に連結する動画 |
| `typewriter_subtitle` | boolean | 字幕のタイプライター表示 |

StyleBertVITS2、Qwen3-TTS、口パクの詳細パラメーターはSwagger UIの `ProjectCreate` スキーマを参照してください。

## 状態と成果物

| メソッド | パス | 内容 |
|---|---|---|
| `GET` | `/api/projects/{project_id}/status` | 状態、進捗、メッセージ、エラー |
| `GET` | `/api/projects/{project_id}` | プロジェクト情報 |
| `GET` | `/api/projects/{project_id}/scenes` | 解析済みシーン |
| `GET` | `/api/projects/{project_id}/download` | 完成動画 |
| `GET` | `/api/projects/{project_id}/chapters` | チャプター情報 |
| `GET` | `/api/projects/{project_id}/chapters.json` | チャプターJSON |
| `POST` | `/api/projects/{project_id}/thumbnail` | サムネイル生成 |
| `GET` | `/api/projects/{project_id}/thumbnail` | サムネイル取得 |

```powershell
$id = "PROJECT_ID"
Invoke-RestMethod "http://localhost:18000/api/projects/$id/status"
Invoke-WebRequest "http://localhost:18000/api/projects/$id/download" -OutFile "$id.mp4"
```

## 一覧・中断・削除

| メソッド | パス | 内容 |
|---|---|---|
| `GET` | `/api/projects` | プロジェクト一覧 |
| `POST` | `/api/projects/{project_id}/cancel` | 実行中または待機中の処理をキャンセル |
| `DELETE` | `/api/projects/{project_id}` | プロジェクトと保存データを削除 |

削除APIは元に戻せません。必要なMP4を先にダウンロードしてください。

## 素材API

| メソッド | パス | 内容 |
|---|---|---|
| `POST` | `/api/assets/logo` | ロゴをアップロード |
| `GET` | `/api/assets/logos` | ロゴ一覧 |
| `POST` | `/api/assets/bgm` | BGMをアップロード |
| `GET` | `/api/assets/bgms` | BGM一覧 |
| `POST` | `/api/assets/bumper` | イントロ・アウトロ等をアップロード |
| `GET` | `/api/assets/bumpers` | バンパー動画一覧 |
| `GET` | `/api/assets/final-calls` | 最終コール素材一覧 |

アップロードは `multipart/form-data` の `file` フィールドを使用します。

```powershell
curl.exe -F "file=@C:\path\to\logo.png" http://localhost:18000/api/assets/logo
```

## エラーの確認

生成失敗時は、最初に状態APIのエラーとワーカーログを確認します。

```powershell
Invoke-RestMethod "http://localhost:18000/api/projects/PROJECT_ID/status"
docker compose logs --tail=200 worker
```

APIはローカル利用を前提としており、認証を備えていません。インターネットへ直接公開しないでください。
