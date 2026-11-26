import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import google_omni_client as omni


class GoogleOmniClientTests(unittest.TestCase):
    def test_start_frame_is_sent_to_image_to_video_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "character.jpg"
            image.write_bytes(b"example-jpeg-data")
            output = root / "scene.mp4"
            response = Mock(ok=True)
            response.json.return_value = {
                "status": "completed",
                "steps": [{"type": "model_output", "content": [{
                    "type": "video", "data": base64.b64encode(b"0" * 100_001).decode("ascii"),
                }]}],
            }
            with patch.object(omni, "API_KEY", "test-key"), patch.object(omni, "CACHE_DIR", root / "cache"), patch.object(
                omni.requests, "post", return_value=response
            ) as post:
                omni.GoogleOmniClient().generate_clip(
                    "Move one hand naturally", "No text", output,
                    ratio="9:16", first_frame_image=image,
                )
            self.assertEqual(output.stat().st_size, 100_001)
            request = post.call_args.kwargs["json"]
            self.assertEqual(request["model"], "gemini-omni-1.2-flash")
            self.assertEqual(request["input"][0]["type"], "image")
            self.assertEqual(base64.b64decode(request["input"][0]["data"]), image.read_bytes())
            self.assertEqual(request["generation_config"]["video_config"]["task"], "image_to_video")
            self.assertEqual(request["response_format"]["aspect_ratio"], "9:16")


if __name__ == "__main__":
    unittest.main()
