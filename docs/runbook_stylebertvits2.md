# 近道君 v2.0 実行手順書（StyleBertVITS2版）

この手順書は、近道君を StyleBertVITS2 音声で起動し、ショート動画を生成するための運用手順です。

## 前提

以下は準備済みです。

- Node.js / npm
- Docker Desktop
- StyleBertVITS2
- 近道君の `.env`

現在の `.env` は StyleBertVITS2 を使う設定です。

```env
TTS_ENGINE=stylebertvits2
STYLEBERTVITS2_URL=http://host.docker.internal:5000
STYLEBERTVITS2_MODEL_ID=3
STYLEBERTVITS2_SPEAKER_ID=0
STYLEBERTVITS2_STYLE=Neutral
```

## 1. StyleBertVITS2 音声サーバーを起動

PowerShellを1つ開きます。

```powershell
cd C:\Users\kanto\short-videoGPT
powershell -ExecutionPolicy Bypass -File .\scripts\start_sbv2.ps1
```

このPowerShellは閉じずに起動したままにします。

確認URL:

```text
http://localhost:5000/docs
http://localhost:5000/models/info
```

## 2. 近道君を起動

別のPowerShellを開きます。

```powershell
cd C:\Users\kanto\short-videoGPT
docker compose up -d --build
```

起動後、ブラウザで開きます。

```text
http://localhost:3000
```

API診断:

```text
http://localhost:18000/api/diagnostics
```

## 3. 動画生成

1. ブラウザで `http://localhost:3000` を開く
2. 台本プリセットを選ぶ
3. 音声欄が `stylebertvits2` になっていることを確認
4. 必要に応じて以下を調整
   - SBV2 モデルID
   - SBV2 スタイル
   - スタイル強度
   - SDP比率
   - ノイズ
5. `生成開始` を押す
6. 生成状況が `completed` になったら MP4 をダウンロード

出力先:

```text
C:\Users\kanto\short-videoGPT\storage\projects\{project_id}\final\final.mp4
```

## 4. 停止方法

近道君を止める:

```powershell
docker compose down
```

StyleBertVITS2を止める:

```powershell
Ctrl + C
```

## 5. 環境確認

起動前にまとめて確認する場合:

```powershell
cd C:\Users\kanto\short-videoGPT
powershell -ExecutionPolicy Bypass -File .\scripts\check_install.ps1
```

## 6. よくあるエラー

### npm が実行できない

PowerShellで `npm` がブロックされる場合は、`npm.cmd` を使います。

```powershell
cd C:\Users\kanto\short-videoGPT\frontend
npm.cmd install
npm.cmd run build
```

### StyleBertVITS2 に接続できない

以下を確認します。

```text
http://localhost:5000/models/info
```

接続できない場合は、PowerShell 1つ目で音声サーバーを起動してください。

```powershell
cd C:\Users\kanto\short-videoGPT
powershell -ExecutionPolicy Bypass -File .\scripts\start_sbv2.ps1
```

### docker compose で Docker config の警告が出る

以下の警告が出ることがあります。

```text
C:\Users\kanto\.docker\config.json: Access is denied
```

`docker compose config` や `docker compose up` が動いていれば、まずは続行できます。
Docker Hub ログインやpullで失敗する場合は、Docker Desktopを通常ユーザーで起動し直してください。

## 7. 日次制作の最短手順

毎日の制作では、基本はこの2つだけです。

PowerShell 1:

```powershell
cd C:\Users\kanto\short-videoGPT
powershell -ExecutionPolicy Bypass -File .\scripts\start_sbv2.ps1
```

PowerShell 2:

```powershell
cd C:\Users\kanto\short-videoGPT
docker compose up --build
```

ブラウザ:

```text
http://localhost:3000
```
