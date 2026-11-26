import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tasks import _apply_lieutenant_colonel_lipsync, _apply_start_frame_character_lipsync


class LieutenantColonelLipSyncTests(unittest.TestCase):
    def test_dx_retries_registered_start_image_when_video_face_detection_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_clip, source_image, audio = (root / name for name in ("scene.mp4", "dx.jpg", "scene.wav"))
            for path in (source_clip, source_image, audio):
                path.touch()
            clips = [source_clip]
            scene = {"speaker": "DXOjisan", "dialogue": [{"speaker": "DXOjisan"}],
                     "start_frame_image": "DXおじさん3.jpg", "duration": 5}
            with patch("tasks.lipsync_enabled", return_value=True), \
                    patch("tasks.set_status"), \
                    patch("tasks._resolve_start_frame_image", return_value=source_image), \
                    patch("tasks.generate_lipsync_clip", side_effect=[RuntimeError("Face not detected"), True]) as generate, \
                    patch("tasks.normalize_clip"):
                _apply_start_frame_character_lipsync(
                    project_id="test", scenes=[scene], raw_clips=clips, scene_wavs=[audio],
                    clip_dir=root, output_width=1080, output_height=1920, output_fps=30,
                )
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(generate.call_args_list[0].kwargs["fallback_source_path"], source_clip)
            self.assertEqual(generate.call_args_list[1].kwargs["fallback_source_path"], source_image)
            self.assertEqual(generate.call_args_list[1].kwargs["source_mode"], "image")
            self.assertEqual(clips[0], root / "scene_01_lipsync.mp4")

    def test_dx_keeps_original_video_if_both_lipsync_attempts_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_clip, source_image, audio = (root / name for name in ("scene.mp4", "dx.jpg", "scene.wav"))
            for path in (source_clip, source_image, audio):
                path.touch()
            clips = [source_clip]
            scene = {"speaker": "DXOjisan", "dialogue": [{"speaker": "DXOjisan"}],
                     "start_frame_image": "DXおじさん3.jpg", "duration": 5}
            with patch("tasks.lipsync_enabled", return_value=True), \
                    patch("tasks.set_status"), \
                    patch("tasks._resolve_start_frame_image", return_value=source_image), \
                    patch("tasks.generate_lipsync_clip", side_effect=RuntimeError("Face not detected")) as generate, \
                    patch("tasks.normalize_clip") as normalize:
                _apply_start_frame_character_lipsync(
                    project_id="test", scenes=[scene], raw_clips=clips, scene_wavs=[audio],
                    clip_dir=root, output_width=1080, output_height=1920, output_fps=30,
                )
            self.assertEqual(generate.call_count, 2)
            normalize.assert_not_called()
            self.assertEqual(clips[0], source_clip)

    def test_dx_ojisan_uses_own_generated_clip_and_audio_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = [root / f"scene_{i}.mp4" for i in range(3)]
            audio = [root / f"scene_{i}.wav" for i in range(3)]
            for path in clips + audio:
                path.touch()
            scenes = [
                {"speaker": "DXOjisan", "dialogue": [{"speaker": "DXOjisan"}],
                 "start_frame_image": "DXおじさん.jpg", "duration": 5},
                {"speaker": "GPT", "dialogue": [{"speaker": "GPT"}],
                 "start_frame_image": "DXおじさん.jpg", "duration": 5},
                {"speaker": "DXOjisan", "dialogue": [{"speaker": "DXOjisan"}, {"speaker": "GPT"}],
                 "start_frame_image": "DXおじさん.jpg", "duration": 5},
            ]
            with patch("tasks.lipsync_enabled", return_value=True), \
                    patch("tasks.set_status"), \
                    patch("tasks.generate_lipsync_clip", return_value=True) as generate, \
                    patch("tasks.normalize_clip"):
                _apply_start_frame_character_lipsync(
                    project_id="test", scenes=scenes, raw_clips=clips, scene_wavs=audio,
                    clip_dir=root, output_width=1080, output_height=1920, output_fps=30,
                )
            generate.assert_called_once()
            self.assertEqual(generate.call_args.kwargs["speaker"], "DXOjisan")
            self.assertEqual(generate.call_args.kwargs["fallback_source_path"], root / "scene_0.mp4")
            self.assertEqual(generate.call_args.kwargs["audio_path"], root / "scene_0.wav")
            self.assertTrue(generate.call_args.kwargs["use_generated_source"])
            self.assertFalse(generate.call_args.kwargs["allow_static_fallback"])
            self.assertEqual(clips[1], root / "scene_1.mp4")
            self.assertEqual(clips[2], root / "scene_2.mp4")

    def test_only_colonel_start_frame_scene_uses_its_own_video_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = [root / f"scene_{i}.mp4" for i in range(3)]
            audio = [root / f"scene_{i}.wav" for i in range(3)]
            for path in clips + audio:
                path.touch()
            scenes = [
                {"speaker": "LieutenantColonel", "dialogue": [{"speaker": "LieutenantColonel"}],
                 "start_frame_image": "中佐静止画アニメ.jpg", "duration": 5},
                {"speaker": "GROCK", "dialogue": [{"speaker": "GROCK"}],
                 "start_frame_image": "中佐静止画アニメ.jpg", "duration": 5},
                {"speaker": "LieutenantColonel", "dialogue": [{"speaker": "LieutenantColonel"}, {"speaker": "GPT"}],
                 "start_frame_image": "中佐静止画アニメ.jpg", "duration": 5},
            ]
            with patch("tasks.lipsync_enabled", return_value=True), \
                    patch("tasks.set_status"), \
                    patch("tasks.generate_lipsync_clip", return_value=True) as generate, \
                    patch("tasks.normalize_clip"):
                _apply_lieutenant_colonel_lipsync(
                    project_id="test", scenes=scenes, raw_clips=clips, scene_wavs=audio,
                    clip_dir=root, output_width=1080, output_height=1920, output_fps=30,
                )
            generate.assert_called_once()
            self.assertEqual(generate.call_args.kwargs["fallback_source_path"], root / "scene_0.mp4")
            self.assertEqual(generate.call_args.kwargs["audio_path"], root / "scene_0.wav")
            self.assertTrue(generate.call_args.kwargs["use_generated_source"])
            self.assertFalse(generate.call_args.kwargs["allow_static_fallback"])
            self.assertEqual(generate.call_args.kwargs["mouth_box"], "685,850,885,990")
            self.assertEqual(clips[1], root / "scene_1.mp4")
            self.assertEqual(clips[2], root / "scene_2.mp4")


if __name__ == "__main__":
    unittest.main()
