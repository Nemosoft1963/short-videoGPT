import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch

from services.minimax_client import MiniMaxClient
from services.runway_client import RunwayClient
from services.scene_planner import _parse_script_block, build_scenes
from services.voice_profiles import get_voice_profile
from tasks import _full_frame_major_source, _resolve_start_frame_image, _register_scenario_image_clip, _scene_clip_cache_payload


class ImageToVideoTests(unittest.TestCase):
    def test_start_frame_engine_override_isolated_to_target_scene_cache(self):
        project = {"format": "short_vertical", "start_frame_engine_overrides": {"5": "runway"}}
        scene = {"scene_id": 5, "start_frame_image": "DXおじさん3.jpg", "_start_frame_sha256": "image-hash", "duration": 5}
        runway = _scene_clip_cache_payload(project, scene, "veo_lite", 1080, 1920, 30, None)
        minimax = _scene_clip_cache_payload({"format": "short_vertical"}, scene, "veo_lite", 1080, 1920, 30, None)
        self.assertEqual(runway["start_frame_engine"], "runway")
        self.assertNotIn("start_frame_engine", minimax)

    def test_dx_ojisan_start_frame_and_voice_are_distinct_from_legacy_analyst(self):
        script = (
            "映像：[start_frame:DXおじさん3.jpg] タブレットを示し、うなずきながら説明する。カメラ固定。\n"
            "DXおじさん：数字の意味を一緒に見ていきましょう。\n"
            "字幕：数字の意味を確認する。"
        )
        scenes = build_scenes({"script": script, "format": "short_vertical", "short_timing_mode": "script", "duration": 30})
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["speaker"], "DXOjisan")
        self.assertEqual(scenes[0]["start_frame_image"], "DXおじさん3.jpg")
        self.assertIn("タブレットを示し", scenes[0]["visual_prompt"])
        dx_voice = get_voice_profile("DXおじさん")
        self.assertEqual(dx_voice["model_name"], "jvnv-M1-jp")
        self.assertLess(dx_voice["speed_scale"], 1.0)
        self.assertLess(dx_voice["noise"], 0.4)
        self.assertEqual(dx_voice["pitch_scale"], 0.84)
        self.assertNotEqual(get_voice_profile("分析官K"), get_voice_profile("DXおじさん"))

        analyst_script = script.replace("DXおじさん：", "分析官K：")
        analyst_scene = build_scenes({"script": analyst_script, "format": "short_vertical", "short_timing_mode": "script", "duration": 30})[0]
        self.assertEqual(analyst_scene["speaker"], "DXOjisan")
        for old_image in ("DXおじさん.jpg", "DXおじさん2.jpg"):
            legacy_scene = build_scenes({"script": analyst_script.replace("DXおじさん3.jpg", old_image),
                                         "format": "short_vertical", "short_timing_mode": "script", "duration": 30})[0]
            self.assertEqual(legacy_scene["speaker"], "DXOjisan")

    def test_full_frame_major_uses_registered_video_as_underlay(self):
        project = {"analystk_lipsync_source_set": "anime", "analystk_lipsync_display_mode": "full"}
        scene = {"scene_id": 5, "speaker": "Major", "motoko_lipsync": True, "lipsync_display_mode": "full"}
        source = Path("/storage/assets/analystk_lipsync_source.mp4")
        with patch("tasks.lipsync_enabled", return_value=True), \
                patch("tasks.configured_lipsync_source", return_value=source) as configured:
            self.assertEqual(_full_frame_major_source(project, scene), source)
            configured.assert_called_once_with("video", "anime")
            self.assertIsNone(_full_frame_major_source(project, {**scene, "start_frame_image": "image.jpg"}))
            self.assertIsNone(_full_frame_major_source(project, {**scene, "lipsync_display_mode": "bottom"}))

    def test_minimax_first_frame_payload_and_image_sensitive_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "frame.jpg"
            image.write_bytes(b"sample image bytes")
            output = Path(directory) / "result.mp4"
            client = MiniMaxClient.__new__(MiniMaxClient)
            client.headers = {"Authorization": "Bearer test"}
            response = Mock(ok=True, status_code=200)
            response.json.return_value = {"task_id": "test-task", "base_resp": {"status_code": 0}}
            with patch("services.minimax_client.requests.post", return_value=response) as post, \
                    patch.object(client, "_load_cached_video", return_value=False), \
                    patch.object(client, "_poll_file_id", return_value="file-id"), \
                    patch.object(client, "_retrieve_download_url", return_value="https://example.test/video"), \
                    patch.object(client, "_download"), \
                    patch.object(client, "_save_video_cache") as save:
                client.generate_clip("A classroom lecture", "", output, first_frame_image=image)
            payload = post.call_args.kwargs["json"]
            self.assertTrue(payload["first_frame_image"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(payload["model"], "MiniMax-Hailuo-2.3")
            self.assertNotIn("fast_pretreatment", payload)
            self.assertEqual(len(save.call_args.args[2]["first_frame_sha256"]), 64)

    def test_runway_uses_registered_start_frame_without_generating_another_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "frame.jpg"
            image.write_bytes(b"registered image")
            output = Path(directory) / "result.mp4"
            client = RunwayClient.__new__(RunwayClient)
            client.headers = {"Authorization": "Bearer test"}
            posted = Mock(ok=True)
            posted.json.return_value = {"id": "task-test"}
            polled = Mock(ok=True)
            polled.json.return_value = {"status": "SUCCEEDED", "output": ["https://example.test/video.mp4"]}
            with patch("services.runway_client.VIDEO_CACHE_DIR", Path(directory) / "cache"), \
                    patch("services.runway_client.requests.post", return_value=posted) as post, \
                    patch("services.runway_client.requests.get", return_value=polled), \
                    patch("services.runway_client.time.sleep"), \
                    patch.object(client, "_generate_image") as generate_image, \
                    patch.object(client, "_download", side_effect=lambda url, path: path.write_bytes(b"video")):
                client.generate_clip("A classroom lecture", "", output, first_frame_image=image)
            payload = post.call_args.kwargs["json"]
            self.assertTrue(payload["promptImage"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(payload["model"], "gen4_turbo")
            generate_image.assert_not_called()
            self.assertEqual(output.read_bytes(), b"video")

    def test_clip_tag_selects_registered_full_scene_asset(self):
        clip_id = "clip_" + "a" * 32
        parsed = _parse_script_block(
            f"映像：[clip:{clip_id}]\n中佐：ここから説明します。\n字幕：ここから説明します。",
            "fallback",
        )
        self.assertEqual(parsed["clip_asset_id"], clip_id)
        self.assertEqual(parsed["dialogue"][0]["speaker"], "LieutenantColonel")

    def test_clip_tag_accepts_japanese_filename(self):
        parsed = _parse_script_block(
            "映像：[clip:ターニャの講義動画S.mp4]\n中佐：ここから説明します。",
            "fallback",
        )
        self.assertEqual(parsed["clip_asset_id"], "ターニャの講義動画S.mp4")

    def test_script_start_frame_keeps_written_motion_prompt(self):
        script = (
            "映像：[start_frame:ターニャのリアル静止画.jpg] 黒板の前で自然に瞬きし、手を上げて説明する。\n"
            "中佐：ここから説明します。\n字幕：ここから説明します。"
        )
        scenes = build_scenes({"script": script, "format": "short_vertical", "short_timing_mode": "script", "duration": 30})
        self.assertEqual(scenes[0]["start_frame_image"], "ターニャのリアル静止画.jpg")
        self.assertEqual(scenes[0]["visual_prompt"], "黒板の前で自然に瞬きし、手を上げて説明する。")

    def test_start_frame_requires_motion_and_excludes_clip(self):
        with self.assertRaisesRegex(ValueError, "動き・内容"):
            _parse_script_block("映像：[start_frame:画像.jpg]\n字幕：確認", "fallback")
        with self.assertRaisesRegex(ValueError, "両方"):
            _parse_script_block("映像：[start_frame:画像.jpg] [clip:動画.mp4] 手を振る。", "fallback")

    def test_registered_image_resolves_and_scenario_video_is_listed(self):
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "images"
            clip_dir = Path(directory) / "clips"
            source_dir.mkdir()
            image_id = "img_" + "a" * 32
            image_path = source_dir / f"{image_id}.jpg"
            image_path.write_bytes(b"image bytes")
            (source_dir / f"{image_id}.json").write_text(json.dumps({
                "id": image_id, "name": "開始画像.jpg", "filename": image_path.name,
            }), encoding="utf-8")
            raw_path = Path(directory) / "raw.mp4"
            raw_path.write_bytes(b"sample video bytes")
            scene = {
                "scene_id": 1,
                "start_frame_image": "開始画像.jpg",
                "_start_frame_sha256": "a" * 64,
                "visual_prompt": "手を上げて説明する。",
            }
            with patch("tasks.SOURCE_IMAGE_DIR", source_dir), patch("tasks.VIDEO_CLIP_DIR", clip_dir):
                self.assertEqual(_resolve_start_frame_image("開始画像.jpg"), image_path)
                _register_scenario_image_clip("project-test", {"title": "講義"}, scene, raw_path)
                _register_scenario_image_clip("project-test", {"title": "講義"}, scene, raw_path)
            self.assertEqual(len(list(clip_dir.glob("clip_*.json"))), 1)
            metadata = json.loads(next(clip_dir.glob("clip_*.json")).read_text(encoding="utf-8"))
            self.assertTrue(metadata["filename"].startswith("講義_場面01_"))
            self.assertEqual(metadata["status"], "ready")


if __name__ == "__main__":
    unittest.main()
