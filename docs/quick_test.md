# クイックテスト

1. `.env.example` を `.env` にコピー
2. `docker compose up -d --build`
3. `http://localhost:3000` を開く
4. モデルは `mock 動作確認` のまま生成
5. 完成後に MP4 をダウンロード

この段階ではAI映像ではなく、字幕・音声・結合・Web UI・ジョブ管理の確認を行います。

追加音声サーバーがない環境では、`.env` の `TTS_ENGINE=gtts` またはUIのgTTSを選択してください。
