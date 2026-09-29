"""Build a small Style-Bert-VITS2 trial corpus from the Qwen3 AnalystK voice."""

from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL_NAME = "少佐"
DEFAULT_INSTRUCT = (
    "冷静で抑制された女性分析官の声。低めで芯があり、控えめに艶のある落ち着いた声質。"
    "標準日本語で一語ずつ明瞭に発音し、句読点で長く溜めず、自然な間合いで話す。"
)

LINES = [
    "状況を整理します。まず、確認できた事実から見ていきましょう。",
    "結論を急ぐ必要はありません。重要なのは、判断の根拠を失わないことです。",
    "表面に見えている数字だけでは、全体の構造を正確には捉えられません。",
    "この設計には、見落としてはいけない前提条件があります。",
    "現場では、理論どおりに進まない事態が必ず発生します。",
    "必要なのは、問題を小さく分けて、一つずつ確実に処理することです。",
    "異常を検知しました。原因の候補を優先順位に沿って確認します。",
    "いま注目すべきなのは、結果ではなく、そこに至った過程です。",
    "その説明には矛盾があります。時系列をもう一度確認してください。",
    "情報が不足しています。推測と事実を明確に分離しましょう。",
    "数字は正直です。ただし、数字の見せ方が正直とは限りません。",
    "五つの要点に分ければ、この問題は理解しやすくなります。",
    "第一の論点は費用です。第二の論点は継続性です。",
    "人件費と外注費を比較し、将来の負担まで含めて判断します。",
    "控除の条件を確認しなければ、最終的な金額は確定できません。",
    "借入を増やす前に、返済計画と資金の流れを確認する必要があります。",
    "消費税の闇という言葉だけで、複雑な制度を説明することはできません。",
    "輸出還付の仕組みは、感情ではなく制度として検証すべきです。",
    "雇用保護には利点があります。一方で、副作用も無視できません。",
    "人頭税という制度は、負担の公平性という観点から検討が必要です。",
    "重複督促が発生した原因を、システムと運用の両面から調査します。",
    "訪問介護の現場では、数字に表れない負担が積み重なっています。",
    "医療崩壊を避けるには、短期対策と長期設計の両方が必要です。",
    "社会保険、つまり社保の負担は、企業と働く人の双方に影響します。",
    "善意だけでは、持続可能な仕組みを設計できません。",
    "信念を持つことと、事実を無視することは同じではありません。",
    "真実は一つでも、そこへ至る道筋は一つとは限りません。",
    "鏡の国に迷い込んだように、原因と結果が逆転して見えます。",
    "物語や寓話は、複雑な問題を理解するための有効な手段です。",
    "四文字の言葉だけでは、現実の複雑さを表現しきれません。",
    "外された条件を戻し、設計図を最初から確認します。",
    "爆発的な変化ほど、静かな兆候から始まるものです。",
    "瀬戸際に立ったときこそ、冷静な判断が求められます。",
    "後ろにある情報も確認してください。重要な手掛かりがあります。",
    "ここに留まる理由はありません。次の段階へ進みましょう。",
    "輝いている部分だけを見れば、影にある問題を見失います。",
    "具体的な条件を示してください。それが検証の出発点になります。",
    "誠実な説明には、都合の悪い事実も含まれているはずです。",
    "夢から覚めたあとに残るものが、本当に守るべきものです。",
    "情報を集めるだけでは不十分です。意味のある形に整理してください。",
    "俯瞰して見れば、個別の問題が同じ原因につながっていると分かります。",
    "仕組みが社会を蝕む前に、修正可能な箇所を特定します。",
    "上書きする前に、元のデータを保存してください。",
    "近道君、処理状況を確認します。異常があれば直ちに報告してください。",
    "メタ情報と本文を混同すると、分析結果に誤差が生じます。",
    "ジーピーティーの回答も、検証なしに採用してはいけません。",
    "グロックの提案について、実行可能性を確認します。",
    "口座の履歴を確認すると、資金の動きが明確になります。",
    "言葉の選び方によって、同じ事実でも受け取られ方は変わります。",
    "怒りは判断を速めますが、判断の精度を保証しません。",
    "では、次の資料を見てください。ここからが本題です。",
    "確認は完了しました。現時点で、重大な問題は検出されていません。",
    "警告します。この操作を続けると、元の状態には戻せません。",
    "選択肢は二つあります。どちらを選ぶかは、目的によって決まります。",
    "時間は限られています。それでも、確認を省略するべきではありません。",
    "私は事実を示します。最終的に判断するのは、あなた自身です。",
]


def duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def generate(base_url: str, text: str, output: Path, retries: int) -> None:
    payload = json.dumps(
        {
            "text": text,
            "model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "mode": "voice_clone",
            "speaker": "chikamichi",
            "language": "Japanese",
            "instruct": DEFAULT_INSTRUCT,
            "output_format": "wav",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/voice",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=900) as response:
                output.write_bytes(response.read())
            if output.stat().st_size < 10_000:
                raise RuntimeError(f"generated audio is too small: {output.stat().st_size}")
            return
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            if attempt == retries:
                raise
            print(f"retry {attempt}/{retries}: {exc}")
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5005")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/sbv2/sbv2/Style-Bert-VITS2/Data") / MODEL_NAME,
    )
    parser.add_argument("--limit", type=int, default=len(LINES))
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    raw_dir = args.output / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[str] = []
    total_seconds = 0.0

    for index, text in enumerate(LINES[: args.limit], start=1):
        path = raw_dir / f"major_{index:04d}.wav"
        if not path.exists():
            print(f"[{index}/{min(args.limit, len(LINES))}] {text}")
            generate(args.base_url, text, path, args.retries)
        seconds = duration_seconds(path)
        if seconds < 1.0 or seconds > 20.0:
            raise RuntimeError(f"unexpected duration {seconds:.2f}s: {path}")
        total_seconds += seconds
        # Style-Bert-VITS2's --correct_path resolves bare names into Data/<model>/wavs.
        manifest.append(f"{path.name}|{MODEL_NAME}|JP|{text}")

    (args.output / "esd.list").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    (args.output / "corpus_summary.json").write_text(
        json.dumps(
            {
                "model_name": MODEL_NAME,
                "utterances": len(manifest),
                "duration_seconds": round(total_seconds, 2),
                "duration_minutes": round(total_seconds / 60, 2),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"completed: {len(manifest)} utterances, {total_seconds / 60:.2f} minutes")


if __name__ == "__main__":
    main()
