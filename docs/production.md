# 本番環境の運用

このシステムの本番環境は、1台のWindows PC上でDocker Desktopを使い、ブラウザからローカル利用する構成を前提とします。API認証を備えていないため、インターネットへ直接公開しないでください。

## 本番構成の方針

- UI、API、口パクの公開ポートは `127.0.0.1` のみにバインド
- RedisはDockerネットワーク内部だけで使用し、ホストへ公開しない
- Redisデータは `short-video-redis-data` ボリュームへ永続化
- コンテナは異常終了・PC再起動後に復帰する `restart: unless-stopped`
- コンテナログは1ファイル10MB、最大3ファイルに制限
- 映像、音声、素材、プロジェクトは `storage/` に保持
- 口パクサービスは `lipsync` profileを指定した場合だけ起動

## 起動

```powershell
.\scripts\start-production.ps1
```

初回はDockerイメージをビルドするため時間がかかります。スクリプトはAPIのヘルスチェックが成功するまで最大約2分待機します。

口パクを含める場合:

```powershell
docker compose --profile lipsync up -d --build
```

## 状態確認

```powershell
.\scripts\status-production.ps1
```

詳細ログ:

```powershell
docker compose logs --tail=200
docker compose logs -f worker
```

## 停止

```powershell
.\scripts\stop-production.ps1
```

この操作では `storage/` とRedisの名前付きボリュームを削除しません。`docker compose down -v` はキュー情報も削除するため、通常運用では使用しないでください。

## 更新

生成中のジョブがないことを確認してから実施します。

```powershell
git pull --ff-only
docker compose up -d --build --remove-orphans
```

更新後は状態とログを確認します。

```powershell
.\scripts\status-production.ps1
docker compose logs --tail=100 api worker
```

## バックアップ対象

| 対象 | 内容 | 注意 |
|---|---|---|
| `.env` | APIキーと本番設定 | 暗号化またはアクセス制限した場所へ保存 |
| `storage/assets/` | ロゴ、BGM、人物素材、生成キャッシュ | 人物・音源の利用許諾にも注意 |
| `storage/projects/` | プロジェクト履歴と完成動画 | 容量が大きいため世代管理を推奨 |
| `storage/config/` | 発音辞書等 | 台本再現に必要 |

リポジトリ自体はGitHubから復元できます。`storage/diagnostics/` は検証用データのため、通常はバックアップ対象外です。

## 容量管理

容量の主な使用先は `storage/assets/*_cache` と `storage/projects/` です。キャッシュを削除すると再生成時に外部APIの料金や待ち時間が発生する可能性があります。完成動画を退避せずに `storage/projects/` を削除しないでください。

容量確認:

```powershell
Get-ChildItem .\storage -Directory | ForEach-Object {
  $bytes = (Get-ChildItem $_.FullName -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  [PSCustomObject]@{ Name = $_.Name; SizeGB = [math]::Round($bytes / 1GB, 2) }
}
```

## 復旧確認

```powershell
docker compose ps
Invoke-RestMethod http://localhost:18000/api/health
Invoke-RestMethod http://localhost:18000/api/diagnostics
docker compose exec -T redis redis-cli llen rq:queue:video
```

APIが正常でも生成に失敗する場合は、`worker` ログ、TTSサーバー、利用中の動画APIキー・残高の順で確認します。
