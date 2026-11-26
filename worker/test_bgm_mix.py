import unittest
from pathlib import Path
from unittest.mock import patch

from services.ffmpeg_logo_bgm import add_scene_bgms


class SceneBgmTests(unittest.TestCase):
    def test_global_default_fills_untagged_scenes_but_off_stays_silent(self):
        scenes = [
            {"scene_id": 1, "actual_start": 0, "actual_end": 2, "bgm_filename": None},
            {"scene_id": 2, "actual_start": 2, "actual_end": 4, "bgm_filename": "tension_pulse"},
            {"scene_id": 3, "actual_start": 4, "actual_end": 6, "bgm_filename": "off"},
        ]
        with patch("services.ffmpeg_logo_bgm.resolve_bgm", return_value=Path("tension.mp3")), patch(
            "services.ffmpeg_logo_bgm.run"
        ) as run:
            add_scene_bgms(Path("video.mp4"), scenes, Path("output.mp4"), 6, default_bgm=Path("default.mp3"))
        command = run.call_args.args[0]
        self.assertEqual(command.count("default.mp3"), 1)
        self.assertEqual(command.count("tension.mp3"), 1)
        self.assertIn("atrim=0:2.000", command[command.index("-filter_complex") + 1])
        self.assertNotIn("adelay=4000", command[command.index("-filter_complex") + 1])


if __name__ == "__main__":
    unittest.main()
