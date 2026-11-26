import re
import unittest
from pathlib import Path

from services.scene_planner import build_scenes


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "s13_chuusa_qa_04_14.md"
HEADING_RE = re.compile(r"^##\s+S13-(\d{2})[^\n]*$", re.MULTILINE)


def _scene_script(section: str) -> str:
    blocks = []
    current = []
    for line in section.splitlines():
        line = line.strip()
        if line.startswith("映像："):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        elif current and line and line != "---" and not line.startswith("#"):
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return "\n\n".join(blocks)


class S13PresetTests(unittest.TestCase):
    def test_ui_anime_set_overrides_legacy_real_tag(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        headings = list(HEADING_RE.finditer(text))
        index = next(i for i, heading in enumerate(headings) if heading.group(1) == "05")
        script = _scene_script(text[headings[index].end():headings[index + 1].start()])
        self.assertIn("[motoko:real]", script)
        base = {"script": script, "format": "short_vertical", "short_timing_mode": "fixed_57", "duration": 60}

        anime_scenes = build_scenes({**base, "analystk_lipsync_source_set": "anime"})
        real_scenes = build_scenes({**base, "analystk_lipsync_source_set": "real"})
        legacy_scenes = build_scenes(base)

        self.assertEqual(anime_scenes[-1]["speaker"], "Major")
        self.assertEqual(anime_scenes[-1]["lipsync_source_set"], "anime")
        self.assertEqual(real_scenes[-1]["lipsync_source_set"], "real")
        self.assertEqual(legacy_scenes[-1]["lipsync_source_set"], "real")

    def test_episodes_04_to_14_are_parseable(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        headings = list(HEADING_RE.finditer(text))
        self.assertEqual([match.group(1) for match in headings], [f"{number:02d}" for number in range(4, 15)])
        for index, heading in enumerate(headings):
            with self.subTest(episode=heading.group(1)):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
                script = _scene_script(text[heading.end():end])
                scenes = build_scenes({
                    "script": script,
                    "format": "short_vertical",
                    "short_timing_mode": "fixed_57",
                    "duration": 60,
                })
                self.assertEqual(len(scenes), 5)
                # 固定57秒は本編56秒＋最終調整1秒。
                self.assertEqual(sum(scene["duration"] for scene in scenes), 56)
                self.assertEqual(sum(bool(scene.get("start_frame_image")) for scene in scenes), 2)
                self.assertEqual(
                    {scene.get("start_frame_image") for scene in scenes if scene.get("start_frame_image")},
                    {"中佐静止画アニメ.jpg"},
                )
                self.assertEqual(
                    [scene.get("speaker") for scene in scenes],
                    ["GROCK", "LieutenantColonel", "GPT", "LieutenantColonel", "Major"],
                )
                self.assertTrue(all(scene.get("subtitle") for scene in scenes))


if __name__ == "__main__":
    unittest.main()
