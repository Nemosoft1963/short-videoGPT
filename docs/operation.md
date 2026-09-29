# 運用手順

## 通常起動

```powershell
copy .env.example .env
docker compose up --build
```

## 停止

```powershell
docker compose down
```

## ログ確認

```powershell
docker compose logs -f worker
```

## 完成動画の場所

```text
storage/projects/{project_id}/final/final.mp4
```

## 動画生成エンジン

Web UIから Runway、Google Veo、MiniMax Hailuo、MOCを選択します。
ComfyUIは2026-09-22にシステムから削除済みです。

## BGM

BGMを使う場合は以下に置きます。

```text
storage/assets/bgm.mp3
```

画面で「BGMあり」にすると使用されます。

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
