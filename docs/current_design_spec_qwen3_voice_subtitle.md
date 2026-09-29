# 現行設計仕様書: Qwen3-TTS・話者制御・音声/字幕同期

作成日: 2026-05-23  
対象リポジトリ: `short-videoGPT`

## 1. 目的

本仕様は、近道君向け動画生成環境における現行の音声生成、話者ルーティング、音量正規化、字幕同期、映像素材キャッシュの設計を記録する。

主な目的は次の通り。

- 近道君専用のQwen3-TTS音声クローンを利用する
- 台本で指定された話者に応じてTTSエンジンを切り替える
- 分析官Kの声を、冷静・低め・硬質・抑制された分析官ボイスへ寄せる
- 長尺動画で音量が後半だけ大きくなる問題を避ける
- 長い台詞に対して字幕と音声の進行を合わせる
- 音声に対してシーン尺が長すぎることによる間延びを抑える
- 同一映像指示の再生成を避け、既存素材をコピーして高速化する

## 2. 全体構成

主要コンポーネントは以下。

| 領域 | 実装 |
|---|---|
| Web UI | `frontend/` |
| API | `api/app/main.py` |
| Worker | `worker/tasks.py` |
| TTS選択 | `worker/services/tts_factory.py` |
| 話者プロファイル | `worker/services/voice_profiles.py` |
| Qwen3-TTS HTTPクライアント | `worker/services/qwen3_tts_client.py` |
| Qwen3-TTSローカルブリッジ | `tools/qwen3tts_server/server.py` |
| 音声/動画FFmpeg処理 | `worker/services/ffmpeg_service.py` |
| 字幕生成 | `worker/services/subtitle_service.py` |
| シーン生成 | `worker/services/scene_planner.py` |

## 3. 生成フロー

動画生成は `worker/tasks.py::generate_video()` を中心に進む。

1. `project.json` を読み込む
2. `build_scenes()` で台本からシーン配列を作る
3. 各シーンの映像を生成またはキャッシュから復元する
4. 各シーンの音声を話者ごとにTTS生成する
5. シーン音声を尺に合わせる
6. シーン音声ごとに音量・明瞭化正規化する
7. シーン音声を `narration.wav` に連結する
8. 連結後の音声へ固定ラウドネス処理をかけ `narration_stable.wav` を作る
9. ASS/SRT字幕を生成する
10. 映像を結合し、音声をmuxする
11. BGM、字幕、ロゴ、イントロ/アウトロ、最終コールを適用する

最終動画は通常、以下に出力される。

```text
storage/projects/{project_id}/final/final.mp4
```

### 3.1 シーン尺見積もり

台本解析時のシーン尺は、話者セリフまたはナレーションを中心に見積もる。  
同じ発話が `dialogue` と `narration` の両方に入る場合でも二重カウントしない。

```env
SCENE_TIMING_CHARS_PER_SECOND=8.5
SCENE_TIMING_PADDING_SECONDS=0.25
```

`字幕：` と `テキスト：` は表示内容として尺見積もりへ補助的に含めるが、発話本文の重複で尺が過大にならないことを優先する。

## 4. 話者仕様

台本上で指定できる代表的な話者は以下。

### StyleBertVITS2系

| 台本名 | 内部プロファイル | TTS |
|---|---|---|
| `GMN` | `GMN` | StyleBertVITS2 |
| `YT` | `YT` | StyleBertVITS2 |
| `META` | `META` | StyleBertVITS2 |
| `GPT` | `GPT` | StyleBertVITS2 |
| `GROCK`, `Grock`, `GROK` | `GROCK` | StyleBertVITS2 |
| `CLAUDE`, `Claude`, `クロード`, `クロード君` | `CLAUDE` | StyleBertVITS2 |
| `InvestigatorS`, `S`, `調査員S` | `InvestigatorS` | StyleBertVITS2 |

### Qwen3-TTS系

| 台本名 | 内部プロファイル | TTS |
|---|---|---|
| `chikamichi`, `近道`, `近道君` | `chikamichi` | Qwen3-TTS voice_clone |
| `AnalystK`, `K`, `分析官K`, `分析官Ｋ` | `AnalystK` | Qwen3-TTS voice_clone |

現状、`AnalystK` は `chikamichi` のQwen3-TTS登録音声を利用する。

## 5. Qwen3-TTS仕様

### 5.1 HTTP連携

Workerは `worker/services/qwen3_tts_client.py` から、外部Qwen3-TTSブリッジへHTTP接続する。

既定URL:

```env
QWEN3_TTS_URL=http://host.docker.internal:5005
```

Qwen3-TTSブリッジは以下。

```text
tools/qwen3tts_server/server.py
```

主なエンドポイント:

| Endpoint | 用途 |
|---|---|
| `GET /health` | 生存確認、生成設定確認 |
| `GET /voices` | 登録音声一覧 |
| `POST /voices/register` | 音声クローン登録 |
| `POST /voice` | 音声生成 |

`server.py` は起動時にリポジトリ直下の `.env` を読み込み、Qwen3-TTS生成設定を反映する。

### 5.2 現行Qwen3設定

主な `.env` 設定:

```env
TTS_ENGINE=qwen3tts
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base
QWEN3_TTS_MODE=voice_clone
QWEN3_TTS_SPEAKER=chikamichi
QWEN3_TTS_LANGUAGE=Japanese
QWEN3_TTS_DEVICE_MAP=cuda:0
QWEN3_TTS_VOLUME_GAIN=2.4
QWEN3_TTS_SPEED_GAIN=1.0
QWEN3_TTS_TEMPERATURE=0.72
QWEN3_TTS_TOP_P=0.78
QWEN3_TTS_REPETITION_PENALTY=1.08
QWEN3_TTS_MAX_CHARS_PER_REQUEST=40
QWEN3_TTS_CHUNK_PAUSE_SECONDS=0.02
QWEN3_TTS_TRIM_CHUNK_SILENCE=false
QWEN3_TTS_SILENCE_THRESHOLD_DB=-45dB
```

意図:

- `temperature/top_p` は低めにし、感情の揺らぎを抑える
- `speed_gain=1.0` でQwen3-TTS後段の追加加速を行わない
- `volume_gain=2.4` でQwen3生成音声の基礎音量を上げる
- 長台詞は短く分割し、チャンク間にはごく短い無音を入れる

### 5.3 数値読み上げ前処理

TTSへ渡す前に数字をかなへ変換する。

実装:

```text
worker/services/qwen3_tts_client.py::_normalize_text_for_tts()
```

例:

```text
2026年5月23日、売上は1,234万円で18.3%増です。
```

変換後:

```text
にせんにじゅうろくねんごがつにじゅうさんにち、売上はせんにひゃくさんじゅうよんまんえんでじゅうはちてんさんぱーせんと増です。
```

### 5.4 長台詞分割

Qwen3-TTSは長文を一括生成すると、語尾や途中の切れ方が不自然になる場合がある。  
そのため、句読点優先でテキストを分割する。

分割優先:

- `。`
- `、`
- `！`
- `？`
- `!`
- `?`
- `.`

最大文字数:

```env
QWEN3_TTS_MAX_CHARS_PER_REQUEST=60
```

チャンク間無音:

```env
QWEN3_TTS_CHUNK_PAUSE_SECONDS=0.02
```

## 6. 分析官K仕様

`分析官K` は `worker/services/voice_profiles.py` で `AnalystK` に正規化される。

現行コンセプト:

```text
冷静で抑制された女性分析官の声。
低めで芯があり、感情の揺れは少なく、短く断定的に話す。
```

注意:

- 特定作品の特定キャラクター声そのものを複製する設計ではない
- 近道君用の独自話者として、公安・サイバー分析官風の声質に寄せる
- 分析官Kのみ `speed_scale=0.92` を適用し、全体速度より落ち着いたテンポにする

## 6.1 早口防止

短尺動画でも、Qwen3-TTSにはショート用の最低速度 `SHORT_VERTICAL_MIN_VOICE_SPEED` を適用しない。  
また、音声がシーン尺より長い場合でも、強制圧縮は原則 `AUDIO_MAX_TEMPO_COMPRESSION` までに抑える。

```env
AUDIO_MAX_TEMPO_COMPRESSION=1.10
AUDIO_MAX_TAIL_PAD_SECONDS=0.80
AUDIO_MIN_SCENE_DURATION=2.60
SUBTITLE_READ_CHARS_PER_SECOND=8.0
```

これを超える場合は音声を無理に早口化せず、シーン尺側を伸ばす。  
逆に、音声がシーン尺より短すぎる場合は、字幕を読む最低時間を残しつつ、末尾無音が `AUDIO_MAX_TAIL_PAD_SECONDS` を大きく超えないようにシーン尺側を短縮する。  
57秒固定に収める必要がある場合は、台本側のセリフを削ることを優先する。

## 6.2 StyleBertVITS2 長文分割

台本内の話者指定により StyleBertVITS2 が選ばれる場合、長文をそのまま `/voice` に渡すと `422 Unprocessable Entity` になることがある。  
そのため StyleBertVITS2 も Qwen3-TTS と同様に、句読点単位で分割して生成し、短い無音で結合する。

```env
STYLEBERTVITS2_MAX_CHARS_PER_REQUEST=90
STYLEBERTVITS2_CHUNK_PAUSE_SECONDS=0.06
```

## 7. 音量・明瞭化仕様

### 7.1 基本方針

長尺動画で「後半ほど音が大きくなる」現象を避けるため、長尺全体に動的正規化をかけない。

現行方針:

1. 各シーン音声を個別に正規化する
2. 正規化済みシーン音声を連結する
3. 最終ナレーションには固定ラウドネスとリミッターのみ適用する

### 7.2 シーン単位音声正規化

実装:

```text
worker/services/ffmpeg_service.py::normalize_scene_audio()
worker/tasks.py
```

出力例:

```text
audio/scene_01_norm.wav
audio/scene_02_norm.wav
```

主な設定:

```env
SCENE_AUDIO_NORMALIZE=true
NARRATION_LOUDNESS_I=-8
NARRATION_LOUDNESS_LRA=7
NARRATION_LOUDNESS_TP=-0.5
NARRATION_PRE_FILTER_GAIN=0.75
```

明瞭化EQ:

```env
NARRATION_HIGHPASS_FREQUENCY=90
NARRATION_LOW_MUD_GAIN=-1.5
NARRATION_PRESENCE_GAIN=3.0
NARRATION_AIR_GAIN=1.5
```

意図:

- `90Hz` 以下を整理する
- `260Hz` 付近のこもりを少し削る
- `3.2kHz` 付近で明瞭度を上げる
- `6.5kHz` 付近で抜けを足す
- `pre_filter_gain=0.75` でEQ前のクリップを避ける

### 7.3 最終ナレーション正規化

実装:

```text
worker/services/ffmpeg_service.py::stabilize_narration_audio()
```

出力:

```text
audio/narration_stable.wav
```

最終段ではEQを二重適用せず、固定 `loudnorm` と `alimiter` を適用する。

## 8. 字幕仕様

### 8.1 基本方針

字幕は音声の進行に対して遅れないことを優先する。  
台本に `字幕：` が明示されたシーンのみ字幕を表示し、字幕指定がないシーンではナレーションや話者セリフから自動字幕を生成しない。  
長台詞では、字幕を短いイベントへ分割し、文字数に応じて表示時間を配分する。

実装:

```text
worker/services/subtitle_service.py
```

生成形式:

- ASS
- SRT

ASSは最終動画へ焼き込まれる。

### 8.2 表示時間配分

従来はシーン尺を字幕ブロック数で均等割りしていた。  
現行は文字数ベースで表示時間を決定する。

主な設定:

```env
SUBTITLE_MIN_EVENT_SECONDS=0.75
SUBTITLE_MAX_EVENT_SECONDS=2.6
SUBTITLE_CHARS_PER_SECOND=11.5
SUBTITLE_MAX_TAIL_HOLD_SECONDS=0.45
SUBTITLE_TYPEWRITER_RATIO=0.38
```

意図:

- 短い字幕を長く残さない
- 長い字幕には相応の表示時間を与える
- 最後の字幕をシーン末尾まで無理に引き伸ばさない
- タイプライター表示を早め、音声に遅れにくくする

### 8.3 サンプル

8秒の長台詞例:

```text
状況を整理する。感情ではなく、事実から判断する。これは長い台詞なので、句読点で区切って、自然に発話させる必要がある。
```

現行字幕イベント例:

```text
0.00-1.65  状況を整理する。 / 感情ではなく、
1.65-3.86  事実から判断する。 / これは長い台詞なので、
3.86-6.39  句読点で区切って、 / 自然に発話させる必要がある。
```

## 9. 映像素材キャッシュ仕様

### 9.1 目的

画像・映像生成の待ち時間を削減するため、同一または過去プロジェクト内の同一シーン素材を再利用する。

実装:

```text
worker/tasks.py
```

キャッシュ格納:

```text
storage/assets/scene_clip_cache/
```

### 9.2 キャッシュキー

以下をもとにキャッシュキーを作成する。

- `visual_prompt`
- `negative_prompt`
- `duration`
- 選択モデル
- 出力解像度
- FPS
- 背景動画指定

### 9.3 復元順序

1. 共有シーンキャッシュを確認する
2. なければ過去プロジェクトの `scenes.json` を新しい順に確認する
3. 一致するシーンがあれば `clips/scene_XX_raw.mp4` をコピーする
4. 復元後、通常の `normalize_clip()` を通す

## 10. 台本話者指定

台本では以下のように話者を指定できる。

```text
分析官K：状況を整理する。感情ではなく、事実から判断する。
近道君：次に確認すべき点を説明します。
GMN：ここが今回の重要ポイントです。
YT：制度上の注意点があります。
```

`scene_planner.py` は既知話者を検出し、シーンの `dialogue` または `speaker` に反映する。  
Workerは `voice_profiles.py` を使い、話者ごとのTTS設定を解決する。

## 11. 運用確認コマンド

Worker状態:

```powershell
docker compose ps worker
```

Qwen3-TTS health:

```powershell
Invoke-RestMethod -Uri http://localhost:5005/health | ConvertTo-Json -Compress
```

Qwen3-TTS登録音声:

```powershell
Invoke-RestMethod -Uri http://localhost:5005/voices | ConvertTo-Json -Depth 5
```

Worker内の話者確認:

```powershell
docker compose exec -T worker python -c "from services.voice_profiles import get_voice_profile; import json; print(json.dumps(get_voice_profile('分析官K'), ensure_ascii=False, indent=2))"
```

字幕サービス構文確認:

```powershell
docker compose exec -T worker python -m py_compile /app/services/subtitle_service.py
```

## 12. 主要な出力ファイル

| ファイル | 内容 |
|---|---|
| `audio/scene_XX_raw.wav` | TTS直後のシーン音声 |
| `audio/scene_XX.wav` | シーン尺へ調整後の音声 |
| `audio/scene_XX_norm.wav` | シーン単位正規化後の音声 |
| `audio/narration.wav` | シーン音声連結後 |
| `audio/narration_stable.wav` | 最終ナレーション音声 |
| `subtitles/subtitles.ass` | 焼き込み用ASS字幕 |
| `subtitles/subtitles.srt` | SRT字幕 |
| `clips/scene_XX_raw.mp4` | 生成または復元された元映像 |
| `clips/scene_XX.mp4` | 正規化後シーン映像 |
| `final/final.mp4` | 完成動画 |

## 13. 既知の調整ポイント

音量がまだ小さい場合:

- `NARRATION_LOUDNESS_I` を `-9` または `-8` へ上げる
- `QWEN3_TTS_VOLUME_GAIN` を上げる

声が硬すぎる場合:

- `QWEN3_TTS_TEMPERATURE` を `0.78` 程度へ上げる
- `QWEN3_TTS_TOP_P` を `0.82` 程度へ上げる

分析官Kがこもる場合:

- `NARRATION_PRESENCE_GAIN` を上げる
- `NARRATION_LOW_MUD_GAIN` をさらに下げる

字幕がまだ遅い場合:

- `SUBTITLE_CHARS_PER_SECOND` を上げる
- `SUBTITLE_TYPEWRITER_RATIO` を下げる
- `SUBTITLE_MAX_EVENT_SECONDS` を下げる

字幕が速すぎる場合:

- `SUBTITLE_CHARS_PER_SECOND` を下げる
- `SUBTITLE_MIN_EVENT_SECONDS` を上げる
- `SUBTITLE_MAX_EVENT_SECONDS` を上げる

## 14. 現行仕様の要点

- Qwen3-TTSは既存環境へ直接組み込まず、HTTPブリッジで疎結合にしている
- 話者指定により、StyleBertVITS2とQwen3-TTSを混在利用できる
- 分析官KはQwen3-TTSの近道君音声を使う低揺らぎ分析官プリセット
- 数字はTTS前にかな変換する
- 長台詞は句読点で分割し、短い無音を挟んで自然化する
- 音量はシーン単位で正規化し、長尺後半だけ大きくなる問題を避ける
- 字幕は文字数ベースで進行し、長台詞との同期を改善する
- 映像素材は共有キャッシュと過去プロジェクト検索で再利用する
