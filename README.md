# 近道君 / Short Video GPT

日本語台本から、ナレーション、字幕、映像、BGM、ロゴを合成して動画を生成するローカルWebアプリです。縦型ショートと横型動画に対応し、外部の動画生成APIとローカル音声合成を組み合わせて利用できます。

> [!IMPORTANT]
> このリポジトリにAPIキー、音声モデル、生成動画、人物素材は含まれません。外部APIを使うと各サービスの利用料金が発生します。最初の動作確認には、課金のない `mock` モードを使用してください。

## 主な機能

- React + Viteの生成UI
- FastAPI + RQ + Redisによる非同期ジョブ処理
- 縦型ショート（9:16）と標準横型（16:9）
- Runway、Google Veo、MiniMax Hailuo、Luma、ローカルMOC映像
- StyleBertVITS2、Qwen3-TTS、Edge TTS、gTTS
- ASS字幕、BGM、ロゴ、イントロ、アウトロの合成
- FFmpegによるレンダリングとMP4出力
- オプションの分析官K口パク生成
- 台本プリセット、話者指定、発音辞書
- 生成状況、診断、キャンセル、ダウンロード用API

VOICEVOXとComfyUIは現行構成から削除されています。

## システム構成

```text
ブラウザ :3000
    │
    ▼
React UI ──► FastAPI :18000 ──► Redis :6379 ──► RQ Worker
                                                   ├─ TTS
                                                   ├─ 動画生成API
                                                   └─ FFmpeg合成
                                                        │
                                                        ▼
                                                storage/projects/

任意: Lip-sync :7860（Docker Composeの lipsync profile）
```

| ディレクトリ | 内容 |
|---|---|
| `frontend/` | React UIと台本プリセット |
| `api/` | FastAPI、ジョブ登録、素材・成果物API |
| `worker/` | 台本解析、音声・映像生成、FFmpeg処理 |
| `lipsync_service/` | オプションの口パクサービス |
| `scripts/` | Windows用の起動・確認スクリプト |
| `docs/` | 台本仕様、API、各サービスの運用資料 |
| `storage/` | 素材、進行中データ、成果物（Git対象外） |

## 必要環境

### 基本機能

- Windows 11
- Docker Desktop（Docker Compose v2を含む）
- Git
- 空き容量：生成内容に応じて数GB以上を推奨
- 外部APIを使う場合はインターネット接続

Node.js、Python、FFmpegは通常のDocker起動だけならホスト側に必須ではありません。ローカル開発や補助スクリプトを直接実行する場合に必要です。

### オプション機能

- NVIDIA GPU：口パク処理や一部ローカル音声環境
- StyleBertVITS2サーバー：StyleBertVITS2音声を使用する場合
- Qwen3-TTS HTTP bridge：Qwen3-TTSを使用する場合
- 各動画生成サービスのアカウント、利用枠、APIキー

## クイックスタート

PowerShellで実行します。

```powershell
git clone https://github.com/Nemosoft1963/short-videoGPT.git
Set-Location short-videoGPT
Copy-Item .env.example .env
docker compose up -d --build
```

起動後に次を開きます。

| 画面 | URL |
|---|---|
| 生成UI | <http://localhost:3000> |
| APIドキュメント | <http://localhost:18000/docs> |
| ヘルスチェック | <http://localhost:18000/api/health> |
| 診断結果 | <http://localhost:18000/api/diagnostics> |

Windowsでは次の補助スクリプトも利用できます。

```powershell
.\scripts\start.ps1
```

## 最初の動作確認

1. UIを開きます。
2. 動画生成モードは `mock` を選びます。
3. 音声は、追加サーバーが不要な `gtts` または `edge` を選びます。
4. 短い台本を入力して「生成開始」を押します。
5. 完了後、UIのダウンロード操作でMP4を取得します。

`mock` は外部の動画生成APIを呼びません。UI、キュー、音声、字幕、FFmpeg結合の確認に適しています。

## 環境設定

`.env.example` を `.env` にコピーし、利用する機能だけ設定します。`.env` はGit管理対象外です。

### 動画生成サービス

| UI/APIの値 | サービス | 必須設定 | 備考 |
|---|---|---|---|
| `mock` | ローカル確認用 | なし | 初回確認向け |
| `runway` | Runway | `RUNWAY_API_KEY` | 外部API課金に注意 |
| `veo_lite` | Google Veo | `GEMINI_API_KEY` | API利用資格・課金設定が必要 |
| `minimax` | MiniMax Hailuo | `MINIMAX_API_KEY` | 外部API課金に注意 |
| `luma` | Luma Dream Machine | `LUMAAI_API_KEY` | 外部API課金に注意 |

例：MiniMaxを使う場合

```env
VIDEO_ENGINE=minimax
MINIMAX_API_KEY=ここに自分のキーを設定
MINIMAX_MODEL=MiniMax-Hailuo-2.3
```

APIキーを設定した後はコンテナを再作成します。

```powershell
docker compose up -d --build --force-recreate api worker
```

キーの値をREADME、ソースコード、Issue、ログへ貼り付けないでください。

### 音声サービス

| `TTS_ENGINE` | 追加サービス | 主な設定 |
|---|---|---|
| `gtts` | 不要 | なし |
| `edge` | 不要 | なし |
| `stylebertvits2` | ホスト側サーバー | `STYLEBERTVITS2_URL` |
| `qwen3tts` | ホスト側HTTP bridge | `QWEN3_TTS_URL` |

StyleBertVITS2の例：

```env
TTS_ENGINE=stylebertvits2
STYLEBERTVITS2_URL=http://host.docker.internal:5000
STYLEBERTVITS2_MODEL_ID=0
STYLEBERTVITS2_SPEAKER_ID=0
STYLEBERTVITS2_STYLE=Neutral
```

Qwen3-TTSの例：

```env
TTS_ENGINE=qwen3tts
QWEN3_TTS_URL=http://host.docker.internal:5005
QWEN3_TTS_MODE=voice_clone
QWEN3_TTS_SPEAKER=chikamichi
```

詳しい手順は [StyleBertVITS2運用手順](docs/runbook_stylebertvits2.md) と [Qwen3-TTS運用手順](docs/runbook_qwen3_tts.md) を参照してください。

## 台本の基本形式

空行でシーンを区切ります。各シーンには映像、話者の発話、字幕を指定できます。

```text
映像：[graphic:title] 制度の仕組み [bgm:tension_pulse]
ナレーション：数字の裏にある仕組みを確認します。
字幕：数字ではなく、仕組みを見る。

映像：[graphic:flow] 売上 → 仕入 → 納税
分析官K：負担がどこで生まれるのか、順番に追います。
字幕：負担の発生点を追う。
```

- `[graphic:*]`：外部動画APIを使わずローカルで図解を生成
- `[bgm:名前]`：登録済みBGMをシーン単位で指定
- `[insert:素材名]`：画像や動画を挿入
- `[insert:素材名:warning]`：警告枠付きで挿入
- 自然文の `映像：`：選択中の外部動画生成サービスへ送信

対応タグ、話者名、字幕ルールは [台本仕様書](docs/script_spec.md) を参照してください。台本作成AIへ渡す場合は [AI台本入力ガイド](docs/ai_script_input_guide.md) と [AI台本作成ガイド](docs/ai_script_generation_guide_latest.md) を使用できます。

## 素材の配置

UIからアップロードするか、次の場所へ配置します。

```text
storage/assets/logos/       ロゴ画像
storage/assets/bgm/         BGM
storage/assets/inserts/     台本から呼び出す画像・動画
storage/assets/bumpers/     イントロ・アウトロ等
```

生成物は次に保存されます。

```text
storage/projects/{project_id}/final/final.mp4
```

`storage/` はGit管理対象外です。バックアップが必要な成果物は別の保存先へコピーしてください。

## 口パク機能

口パクサービスは標準起動には含まれません。NVIDIA GPUとモデルを準備してから起動します。

```powershell
docker compose --profile lipsync up -d --build
```

`.env` の `LIPSYNC_ENABLED=true` と素材パスも設定してください。詳細は [分析官K口パク運用手順](docs/runbook_analystk_lipsync.md) を参照してください。

## 運用コマンド

```powershell
# 状態確認
docker compose ps

# 全サービスのログ
docker compose logs --tail=200

# ワーカーの追跡
docker compose logs -f worker

# 再起動
docker compose restart

# 設定やイメージを反映して再作成
docker compose up -d --build

# 停止・コンテナ削除（storageの成果物は残る）
docker compose down
```

キュー件数の確認：

```powershell
docker compose exec -T redis redis-cli llen rq:queue:video
```

## APIの基本操作

生成開始：

```http
POST /api/projects
Content-Type: application/json
```

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

主なエンドポイント：

| メソッド | パス | 用途 |
|---|---|---|
| `GET` | `/api/health` | API稼働確認 |
| `GET` | `/api/diagnostics` | TTS・動画API等の診断 |
| `POST` | `/api/projects` | 生成ジョブの登録 |
| `GET` | `/api/projects/{id}/status` | 進捗・エラー確認 |
| `POST` | `/api/projects/{id}/cancel` | キャンセル |
| `GET` | `/api/projects/{id}/download` | 完成MP4の取得 |
| `GET` | `/api/projects` | プロジェクト一覧 |
| `DELETE` | `/api/projects/{id}` | プロジェクト削除 |

全仕様は起動中のSwagger UI（`/docs`）または [API資料](docs/api.md) を参照してください。

## トラブルシューティング

### UIが開かない

```powershell
docker compose ps
docker compose logs --tail=100 frontend api
```

`frontend` と `api` が起動中か確認します。ポート3000または18000が使用中の場合は、該当プロセスを停止するか `docker-compose.yml` のホスト側ポートを変更してください。

### 生成が待機中のまま進まない

```powershell
docker compose ps worker redis
docker compose logs --tail=200 worker
docker compose exec -T redis redis-cli llen rq:queue:video
```

`worker` と `redis` が起動していることを確認します。

### 外部動画APIで失敗する

1. <http://localhost:18000/api/diagnostics> を確認します。
2. `.env` のキー名と利用枠を確認します。
3. `docker compose up -d --force-recreate api worker` で環境変数を反映します。
4. `docker compose logs --tail=200 worker` でHTTPステータスとエラーを確認します。

### 音声が生成されない

- StyleBertVITS2：ホストで <http://localhost:5000/models/info> が開くか確認
- Qwen3-TTS：設定したbridge URLがホストで応答するか確認
- Dockerからホストへは `localhost` ではなく `host.docker.internal` を使用
- 切り分け時は `TTS_ENGINE=gtts` で再確認

### ディスク容量が増える

生成物とキャッシュは `storage/` に蓄積されます。必要な完成動画を退避したうえで、UIまたはAPIから不要なプロジェクトを削除してください。`storage/` 全体を削除すると素材と履歴も失われます。

## セキュリティと公開時の注意

- `.env`、APIキー、認証情報をコミットしないでください。
- 現行APIはローカル利用を前提とし、認証機能を備えていません。
- 3000、18000、6379、7860番ポートをインターネットへ直接公開しないでください。
- URLインサートとYouTube取得は、信頼できる素材だけを指定してください。
- 人物画像、音声、BGM、ロゴ、生成物について、利用許諾と各サービスの規約を確認してください。
- 政策・統計等を扱う台本では、公開前に一次資料と照合してください。

## 関連資料

- [運用手順](docs/operation.md)
- [本番環境の運用](docs/production.md)
- [クイックテスト](docs/quick_test.md)
- [台本仕様書](docs/script_spec.md)
- [API資料](docs/api.md)
- [Google Veo設定](docs/google_veo_lite_setup.md)
- [字幕位置と折り返し](docs/subtitle_position_wrap.md)
- [分析官K口パク運用手順](docs/runbook_analystk_lipsync.md)

## ライセンス

ライセンスファイルはまだ設定されていません。そのため、著作権法上の通常の権利が保持され、第三者による複製・改変・再配布は自動的には許可されません。オープンソースとして再利用を許可する場合は、用途に合うライセンスを別途追加してください。
