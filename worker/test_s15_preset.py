import re
import unittest
from pathlib import Path

from services.scene_planner import build_scenes


SOURCE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "s15_01_20.md"
HEADING = re.compile(r"^##\s+S15-(\d{2})[^\n]*$", re.MULTILINE)


class S15PresetTests(unittest.TestCase):
    def test_twenty_episodes_use_registered_images_and_expected_speakers(self):
        text = SOURCE.read_text(encoding="utf-8")
        matches = list(HEADING.finditer(text))
        self.assertEqual([m.group(1) for m in matches], [f"{i:02d}" for i in range(1, 21)])
        dx_count = 0
        for index, heading in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[heading.end():end].strip().rstrip("-").strip()
            scenes = build_scenes({
                "script": section,
                "format": "short_vertical",
                "short_timing_mode": "script",
                "duration": 60,
                "analystk_lipsync_source_set": "real",
            })
            with self.subTest(episode=heading.group(1)):
                self.assertGreaterEqual(len(scenes), 6)
                self.assertEqual(scenes[-1]["speaker"], "Major")
                self.assertEqual(scenes[-1]["bgm_filename"], "off")
                self.assertIn("登録して、接続を維持しなさい", scenes[-1]["narration"])
                for scene in scenes:
                    image = scene.get("start_frame_image")
                    if image:
                        self.assertIn(image, {"中佐静止画アニメ.jpg", "DXおじさん3.jpg"})
                    if scene["speaker"] == "DXOjisan":
                        dx_count += 1
                        self.assertEqual(image, "DXおじさん3.jpg")
        self.assertEqual(dx_count, 14)


if __name__ == "__main__":
    unittest.main()
