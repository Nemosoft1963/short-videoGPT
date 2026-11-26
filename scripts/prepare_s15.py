"""S15受領台本を既存キャラクター素材に合わせてプリセット用に整形する。"""
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\kanto\Downloads\消費税の闇_S15_01-20_近道君台本_57秒再構成版.md")
TARGET = ROOT / "frontend" / "src" / "s15_01_20.md"
LT_IMAGE = "中佐静止画アニメ.jpg"
DX_IMAGE = "DXおじさん3.jpg"

# 会社の現金支出・雇用・価格転嫁を分析官Kが解説する。
# 値は各話の「中佐」発話のうち何番目を置き換えるか（1始まり）。
DX_SCENES = {
    "02": 3, "03": 3, "04": 3, "06": 3, "07": 3,
    "08": 3, "09": 3, "10": 3, "11": 4, "12": 3,
    "15": 4, "17": 3, "18": 3, "19": 4,
}
HEADING_RE = re.compile(r"^##\s+S15-(\d{2})([^\r\n]*)$", re.MULTILINE)


def scene_blocks(section: str) -> list[str]:
    blocks = []
    current = []
    for raw in section.splitlines():
        line = raw.strip()
        if line.startswith("映像："):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        elif current and line and line != "---" and not line.startswith("#"):
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def prepare(source: Path) -> str:
    raw = source.read_text(encoding="utf-8-sig")
    headings = list(HEADING_RE.finditer(raw))
    if [match.group(1) for match in headings] != [f"{number:02d}" for number in range(1, 21)]:
        raise ValueError("S15-01からS15-20までの見出しが揃っていません")
    output = ["# 消費税の闇 S15 全20話（近道君用）"]
    dx_used = set()
    for index, heading in enumerate(headings):
        number = heading.group(1)
        title = heading.group(2).strip()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(raw)
        blocks = scene_blocks(raw[heading.end():end])
        if len(blocks) < 6:
            raise ValueError(f"S15-{number}: シーン不足")
        lieutenant_index = 0
        updated = []
        for block in blocks:
            block = block.replace("[start_frame:ターニャの税金談義.jpg]", f"[start_frame:{LT_IMAGE}]")
            if re.search(r"(?m)^中佐：", block):
                lieutenant_index += 1
                if DX_SCENES.get(number) == lieutenant_index:
                    if f"[start_frame:{LT_IMAGE}]" not in block:
                        raise ValueError(f"S15-{number}: DX差替え対象に開始画像がありません")
                    block = block.replace(f"[start_frame:{LT_IMAGE}]", f"[start_frame:{DX_IMAGE}]")
                    block = re.sub(r"(?m)^中佐：", "DXおじさん：", block, count=1)
                    dx_used.add(number)
            updated.append(block)
        if not updated[-1].startswith("映像：[motoko:fullscreen]") or "[bgm:off]" not in updated[-1]:
            raise ValueError(f"S15-{number}: 少佐の締め指定がありません")
        output.extend(["", f"## S15-{number}{title}", "", "\n\n".join(updated), "", "---"])
    if dx_used != set(DX_SCENES):
        raise ValueError(f"DX変更漏れ: {set(DX_SCENES) - dx_used}")
    result = "\n".join(output) + "\n"
    if "ターニャの税金談義.jpg" in result:
        raise ValueError("未登録の開始画像名が残っています")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    content = prepare(args.source)
    TARGET.write_text(content, encoding="utf-8")
    print(f"{TARGET}: 20話を準備（分析官K {len(DX_SCENES)}話）")
