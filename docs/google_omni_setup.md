# Google Gemini Omni Flash 動画生成

S15以降の登録静止画からの動画生成は `google_omni` を使います。MiniMaxへの自動切替はありません。

`.env` に以下を設定します。APIキーはGitへ登録しないでください。

```env
VIDEO_ENGINE=google_omni
START_FRAME_VIDEO_ENGINE=google_omni
GEMINI_API_KEY=（Google AI Studioで発行したキー）
GOOGLE_OMNI_MODEL=gemini-omni-1.2-flash
GOOGLE_OMNI_DURATION_SECONDS=6
GOOGLE_OMNI_RESOLUTION=720p
```

台本の `[start_frame:画像名.jpg]` は登録画像をGemini Omni Flashの `image_to_video` 入力に送ります。動画はシーンのナレーション・字幕・BGMとローカルで合成します。Google生成動画自体の音声はナレーションに使いません。`[graphic:*]` はローカル生成です。

Google APIの有料枠と残高が必要です。生成失敗時は別サービスへ無断で切り替えず、状態を確認してください。

- [公式の動画生成ガイド](https://aistudio.google.com/docs/omni.md)
- [モデル仕様・料金](https://aistudio.google.com/docs/models/gemini-omni-flash.md)
- [旧Veoモデルの提供終了](https://aistudio.google.com/docs/deprecations.md)
