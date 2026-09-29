# 運用手順

## 通常起動

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

生成UIは `http://localhost:3000`、APIドキュメントは `http://localhost:18000/docs` です。

## 停止

```powershell
docker compose down
```

## ログ確認

```powershell
docker compose logs -f worker
```

全体の状態と直近ログ:

```powershell
docker compose ps
docker compose logs --tail=200
```

## 再起動と設定反映

単純な再起動:

```powershell
docker compose restart
```

`.env` やコードを反映する場合:

```powershell
docker compose up -d --build --force-recreate
```

## 完成動画の場所

```text
storage/projects/{project_id}/final/final.mp4
```

## 動画生成エンジン

Web UIから Runway、Google Veo、MiniMax Hailuo、Luma、MOCを選択します。
ComfyUIは2026-09-22にシステムから削除済みです。

## BGM

BGMはUIから登録するか、以下に置きます。

```text
storage/assets/bgm.mp3
storage/assets/bgm/
```

画面で「BGMあり」にすると使用されます。

## 診断

```powershell
Invoke-RestMethod http://localhost:18000/api/health
Invoke-RestMethod http://localhost:18000/api/diagnostics
```

外部APIの設定を変更したときは、`api` と `worker` の両方を再作成してください。

## v0.2 追加機能

### 音声と字幕の同期
StyleBertVITS2またはQwen3-TTSで作成した各シーンの音声を、シーン尺に合わせて自動補正します。
音声が長い場合は `atempo` で速度補正し、短い場合は無音を足します。
これにより、字幕の切り替わりと音声のズレを抑えます。

### 音声選択
Web UIの「音声」でStyleBertVITS2またはQwen3-TTSの話者を選択できます。
APIは `/api/voices` から現在のTTSエンジンの話者一覧を返します。
VOICEVOXは2026-09-22にシステムから削除済みです。

### 台本入力
Web UIの「台本」に入力した文章を優先してシーン分割します。
空行で1シーンとして扱います。
各シーンに次の形式で細かい指定もできます。

```text
映像：古い和菓子店の店先。朝の薄い光。
ナレーション：土地2,500万円。それでも、銀行は貸しません。
字幕：土地2,500万円。
それでも、銀行は貸しません。
```

### 字幕サイズ
Web UIで字幕サイズを選択できます。
標準は 72 です。
