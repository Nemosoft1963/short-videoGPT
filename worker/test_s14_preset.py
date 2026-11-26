import re
import unittest
from pathlib import Path

from services.scene_planner import build_scenes


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "s14_chuusa_qa_01_20.md"
HEADING_RE = re.compile(r"^##\s+S14-(\d{2})[^\n]*$", re.MULTILINE)


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


class S14PresetTests(unittest.TestCase):
    def test_twenty_episodes_and_all_scenes_are_parseable(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        headings = list(HEADING_RE.finditer(text))
        self.assertEqual([heading.group(1) for heading in headings], [f"{number:02d}" for number in range(1, 21)])
        total_scenes = 0
        dx_scenes = 0
        for index, heading in enumerate(headings):
            with self.subTest(episode=heading.group(1)):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
                script = _scene_script(text[heading.end():end])
                scenes = build_scenes({
                    "script": script,
                    "format": "short_vertical",
                    "short_timing_mode": "script",
                    "duration": 60,
                    "analystk_lipsync_source_set": "real",
                })
                self.assertGreaterEqual(len(scenes), 5)
                self.assertTrue(all(scene.get("subtitle") for scene in scenes))
                self.assertEqual(scenes[-1]["speaker"], "Major")
                self.assertEqual(scenes[-1]["bgm_filename"], "off")
                self.assertIn("登録して、接続を維持しなさい", scenes[-1]["narration"])
                for scene in scenes:
                    image = scene.get("start_frame_image")
                    if image:
                        self.assertIn(image, {"DXおじさん3.jpg", "中佐静止画アニメ.jpg"})
                    if scene["speaker"] == "DXOjisan":
                        dx_scenes += 1
                        self.assertEqual(image, "DXおじさん3.jpg")
                total_scenes += len(scenes)
        self.assertEqual(total_scenes, 119)
        self.assertEqual(dx_scenes, 12)


if __name__ == "__main__":
    unittest.main()
