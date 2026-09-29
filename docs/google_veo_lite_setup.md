# Google Veo 3.1 Lite 導入メモ

最終更新: 2026-07-23

## 事前準備

1. Googleアカウントで Google AI Studio にログインする。
   - https://aistudio.google.com/

2. Gemini API の API key を作成する。
   - Google AI Studio の「Get API key」から作成する。
   - 近道君では `GEMINI_API_KEY` に設定する。

3. Gemini API の有料ティア/課金を有効化する。
   - Veo 3.1 Lite は無料ティアでは利用不可。
   - 720p は $0.05/秒、1080p は $0.08/秒。

4. 必要に応じて Google Cloud 側で API を有効化する。
   - Gemini API / Generative Language API を利用するプロジェクトに紐づける。
   - Workspace や組織アカウントでは管理者ポリシーでAI Studio/APIキー作成が制限される場合がある。

5. `.env` に以下を追加する。

```env
GEMINI_API_KEY=作成したAPIキー
VEO_MODEL=veo-3.1-lite-generate-preview
VEO_DURATION_SECONDS=6
VEO_RESOLUTION=720p
VEO_API_BASE=https://generativelanguage.googleapis.com/v1beta
VEO_POLL_SECONDS=10
VEO_TIMEOUT_SECONDS=900
```

## 近道君での使い方

- UIの「動画生成モード」で `Google Veo 3.1 Lite 本番生成` を選ぶ。
- 内部値は `veo_lite`。
- S10プリセットは既定で `veo_lite` を使う。
- S10では `[graphic:*]` タグを使わず、`映像：dark ...` の通常プロンプトにする。

## コスト目安

- 6秒1シーン: $0.30
- S10ショート1本 7〜8シーン: 約 $2.10〜$2.40
- 1080pにすると $0.08/秒になり、6秒1シーンなら $0.48。

## 注意

- Veo 3.1 Lite は8秒動画のモデルファミリーだが、近道君では `VEO_DURATION_SECONDS=6` を既定にして低額運用に寄せている。
- 1080pは8秒指定が必要になる場合があるため、まず720pで検証する。
- 生成は非同期Operationのため、1シーンあたり数十秒〜数分待つことがある。
- APIキー未設定時は `/api/diagnostics` の `veo_lite` が `ng` になる。
