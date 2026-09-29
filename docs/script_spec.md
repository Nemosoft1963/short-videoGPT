# 台本仕様書

この仕様書は、`short-videoGPT` に入力する台本テキストの書き方を定義します。対象はフロントエンドの「台本」欄、およびサンプルプリセットの `script` です。

## 基本構造

台本は「シーンブロック」の集合です。1ブロックが1つの映像シーンとして解釈されます。ブロックは空行で区切ります。

```text
映像：[graphic:meeting_room]
GMN：今日の議題を始めます。
GPT：まず、確認された事実から整理します。
字幕：事実から整理する。

映像：[graphic:talker_GROCK] 27,784件
Grock：これは単なる数字じゃない。現場で起きている停止命令だ。
字幕：27,784件。
```

## 推奨ブロック形式

各ブロックは、次の順番で書くことを推奨します。

```text
映像：映像指示または [graphic:*] タグ
話者名：セリフ
話者名：セリフ
字幕：画面下部に出す字幕
テキスト：画面上部などに固定表示する補助テキスト
```

`字幕：` を省略した場合、セリフまたはナレーションから自動的に字幕が作られます。

## 対応ラベル

使用できるラベルは以下です。

| ラベル | 用途 |
|---|---|
| `映像：` | シーンの映像指定 |
| `ナレーション：` | ナレーション音声 |
| `字幕：` | 字幕テキスト |
| `テキスト：` | 画面上に焼き込む固定テキスト |
| `visual:` | `映像：` の英語別名 |
| `narration:` | `ナレーション：` の英語別名 |
| `subtitle:` | `字幕：` の英語別名 |
| `overlay:` | `テキスト：` の英語別名 |

## 対応話者

会話形式では、以下の話者名を使えます。

```text
GMN
分析官K
調査員S
YT
META
GPT
Grock
GROCK
CLAUDE
クロード
クロード君
```

全角の `ＧＭＮ`、`ＹＴ`、`ＭＥＴＡ`、`ＧＰＴ` も一部対応していますが、安定運用では半角英字を推奨します。

## Graphicタグ

`[graphic:*]` を使うと、Runwayなどの映像生成を使わず、ローカルのffmpeg合成で映像を作ります。安定性が高く、会議室・テキスト・グラフ系に向いています。

| タグ | 用途 |
|---|---|
| `[graphic:meeting_room]` | 会議室画面 |
| `[graphic:talker_GMN]` | GMNを強調した会議室 |
| `[graphic:talker_分析官K]` | 分析官Kを強調した会議室 |
| `[graphic:talker_調査員S]` | 調査員Sを強調した会議室 |
| `[graphic:talker_YT]` | YTを強調した会議室 |
| `[graphic:talker_META]` | METAを強調した会議室 |
| `[graphic:talker_GPT]` | GPTを強調した会議室 |
| `[graphic:talker_GROCK]` | Grockを強調した会議室 |
| `[graphic:talkers_GMN+YT]` | 複数話者を同時強調 |
| `[graphic:title]` | タイトル画面 |
| `[graphic:dark_text]` | 暗色背景の強調テキスト |
| `[graphic:dark_office]` | `dark_text` と同義。暗色背景の強調テキスト |
| `[graphic:light_text]` | 明色背景の説明テキスト |
| `[graphic:bar_chart]` | 簡易棒グラフ。数値比較のほか `増` `減` `横ばい` などの状態語も使用可 |
| `[graphic:flow]` | フロー図 |
| `[graphic:sepia]` | 古い資料風、回想風 |
| `[graphic:ultra_bold_title:*]` | タイトル画面。接尾語は演出名として受理 |

例:

```text
映像：[graphic:bar_chart] 令和4年度:27784 令和5年度:42072
YT：差押執行事業所は、令和5年度に4万件を超えています。
字幕：差押執行事業所、令和5年度 42,072件。

映像：[graphic:bar_chart] 利益:0 社保:増 消費税:残 延滞金:増
GPT：ここに延滞金と差押えが乗ると、会社の現金が止まります。
字幕：延滞金と差押えで、現金が止まる。
```

## Insertタグ

`[insert:*]` は、別の画像・動画・URL素材を現在のシーンに重ねる指定です。

### ローカル素材

素材は主に次の場所に置きます。

```text
storage/assets/inserts/
storage/inserts/
```

対応拡張子:

```text
.mp4 .mov .webm .mkv .jpg .jpeg .png .webp
```

例:

```text
映像：[graphic:meeting_room] [insert:graph_30k_over]
YT：差押え件数の推移を見てください。
```

拡張子付きでも指定できます。

```text
映像：[graphic:meeting_room] [insert:news_starvation.png]
```

日本語ファイル名も使用できますが、運用上は英数字IDを推奨します。

```text
映像：[graphic:meeting_room] [insert:外と内からの緩慢なる死の行進.PNG]
```

### URL素材

画像URLまたは動画URLを直接指定できます。

```text
映像：[graphic:meeting_room] [insert:https://example.com/news.png]
```

YouTube URLの場合、`yt-dlp` で動画を取得し、冒頭部を自動で切り出します。切り出し秒数は `INSERT_YOUTUBE_SECONDS` で変更できます。デフォルトは6秒です。

```text
映像：[graphic:meeting_room] [insert:https://youtu.be/VIDEO_ID]
```

## Warningレイヤー

ニュース切り抜き、衝撃画像、強い事実提示には `warning` を付けます。

```text
映像：[graphic:meeting_room] [insert:news_starvation:warning]
GPT：この手続きは、相手の生存確認を放棄した免責手続きに変わる瞬間があります。
字幕：正しい手順が、命を見失う。
```

`warning` 指定時の挙動:

- 背景の会議室を維持
- インサート画像/動画を画面中央に表示
- 不透明度は85%
- 赤い点滅アラート枠を付与
- デジタルノイズと軽いグリッチ演出を付与
- 複数話者にシーン分割されても警告レイヤーを維持

次の書き方も可能です。

```text
[insert:news_starvation warning]
[insert:news_starvation:warning]
[insert:https://example.com/news.png:warning]
[insert:https://youtu.be/VIDEO_ID:warning]
```

また、台本内に以下のような語が含まれる場合は、自動でwarning扱いになります。

```text
餓死
死亡
自殺
破産
倒産
差押
差し押さえ
凍結
危機
警告
号外
緊急
urgent
crisis
warning
alert
```

ただし、演出を確実にしたい場合は `:warning` を明示してください。

## 通常映像プロンプト

`[graphic:*]` を使わずに自然文を書くと、選択中の映像生成モードに渡されます。

```text
映像：A quiet Japanese logistics center exterior at midnight, documentary style, no readable text.
GMN：社会の血管は、静かに焼き切られている。
```

Runway使用時は外部生成になるため、失敗や待ち時間が発生します。安定した会議・図解・テキスト表現は `[graphic:*]` を推奨します。

## シーン分割ルール

空行でブロックを分けると、別シーンになります。

```text
映像：[graphic:title] 第一章
ナレーション：ここから本題に入ります。

映像：[graphic:meeting_room]
GMN：では始めます。
```

1ブロック内に複数話者がいる場合、内部的には話者ごとの短いシーンへ分割されます。

```text
映像：[graphic:meeting_room]
GMN：まず概要です。
GPT：次に根拠です。
Grock：最後に結論だ。
```

通常のインサートは最初の発話にだけ付きます。`warning` インサートは分割後の各発話にも維持されます。

## 字幕

`字幕：` は画面下部の字幕です。複数行も可能です。

```text
字幕：30年後のために、
今を殺すな。
```

長すぎる字幕は折り返しや省略の対象になります。短く、強い文を推奨します。

## テロップとテキスト

元台本の `テロップ：` は、現行パーサーでは専用ラベルではありません。画面に固定表示したい場合は `テキスト：` を使ってください。

```text
テキスト：1. YouTubeチャンネルへ登録
2. note総括記事を共有
3. 30年後のために、今を殺すな。
```

発話させたい場合は、通常の話者セリフにしてください。

```text
GMN：YouTubeチャンネルへ登録し、note総括記事を共有してください。
```

## BGM指定

台本からシーン単位で登録済みBGMを指定できます。対象は `/api/assets/bgms` に出るファイル、つまり `storage/assets/bgm/` 配下の音声ファイルです。

推奨はタグ形式です。`[insert:*]` や `[graphic:*]` と同じ行に並べられるため、映像指示と組み合わせて使えます。

```text
映像：[graphic:title] 第1章 [bgm:serious_doc]
ナレーション：ここから本題に入ります。
字幕：ここから本題。

映像：[graphic:flow] 売上 → 仕入 → 差額 [insert:graph_30k_over:warning] [bgm:tension_pulse.mp3]
YT：この差額が、現場の資金繰りを圧迫します。
字幕：差額が資金繰りを圧迫する。
```

ラベル形式も使えます。拡張子なしでも、ファイル名でも指定できます。

```text
BGM: nostalgic_piano
映像：quiet Japanese old shopping street at dusk, documentary style
GMN：ここで、現場の空気を見てください。
```

指定ルール:
- `[bgm:serious_doc]` は `serious_doc.mp3` のような拡張子違いも解決します。
- `[bgm:tension_pulse.mp3]` は完全なファイル名として解決します。
- `[bgm:off]` / `[bgm:none]` / `[bgm:なし]` はBGM指定なしとして扱います。
- 台本でBGM指定がある場合、画面側の `BGMあり` がOFFでも台本指定を優先して合成します。
- 隣接するシーンで同じBGMを指定した場合は、同一曲をシーン境界で頭出しせず連続再生します。
- 台本指定がない場合は従来通り、画面側の `BGMあり` / `BGM自動選択` / `bgm.mp3` の設定を使います。

## Markdown台本の扱い

外部で作った台本に以下が含まれる場合、そのまま貼るより整形を推奨します。

```text
### 【第一章】
**映像：** ...
**GPT：** ...
---
```

推奨変換:

```text
映像：...
GPT：...
字幕：...
```

Markdown見出しや装飾は、生成には不要です。

## 事実表現の注意

数字・年度・順位・政策名は、可能な限り一次資料に合わせてください。

例:

```text
令和4年度の差押執行事業所は27,784件。
令和5年度の差押執行事業所は42,072件。
```

推測や論評は、事実と分けて書くと安全です。

```text
YT：一次資料では、令和5年度の差押執行事業所は42,072件です。
Grock：この数字は、現場にとっては警告音だ。
```

## 推奨サンプル

```text
映像：[graphic:meeting_room] [insert:slow_death_march:warning]
GMN：誰も、悪意を持って引き金を引いたわけではない。しかし、社会の血管は一本ずつ、確実に焼き切られている。
GPT：調査の結果、恐るべき病理が浮かび上がりました。組織が徴収という業務に過剰適応し、生命維持とのバランスを失った構造的な無責任さです。
字幕：静かなる崩壊。

映像：[graphic:talker_YT] [insert:graph_30k_over:warning]
YT：令和4年度の差押執行事業所は27,784件。令和5年度には42,072件です。
Grock：これは単なる数字じゃない。現場で起きている停止命令だ。
字幕：差押えは、現場の血流を止める。

映像：[graphic:talker_GPT] [insert:news_starvation:warning]
GPT：連絡、無回答、連絡、無回答、執行。この一見丁寧なプロセスが、相手の生存確認を放棄した免責手続きに変わる瞬間があります。
META：組織が正しく動くほど、現場では命が消えていく。
字幕：正しい手順が、命を見失う。
```

## チェックリスト

生成前に以下を確認してください。

- 各シーンは空行で区切られている
- `映像：` が各ブロックの先頭付近にある
- 話者名は `GMN`、`YT`、`META`、`GPT`、`Grock` などの対応名になっている
- 衝撃画像には `[insert:素材名:warning]` を付けている
- インサート素材は `storage/assets/inserts/` に置いている
- YouTube URLを使う場合、冒頭切り出しで問題ない内容か確認している
- シーン別BGMを使う場合、`[bgm:ファイル名]` が登録済みBGM名と一致している
- 事実・数字・年度は一次資料と照合済み
