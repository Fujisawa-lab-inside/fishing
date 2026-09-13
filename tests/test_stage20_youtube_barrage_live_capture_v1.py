from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import stage20_youtube_barrage_live_capture_v1 as capture


class YouTubeBarrageLiveCaptureTests(unittest.TestCase):
    def test_01_source_contract_preserves_positive_only_semantics(self) -> None:
        config = capture.load_config()
        self.assertEqual(config["targetView"]["overlayTokens"], ["遠賀川水系遠賀川", "右岸", "2k000"])
        self.assertEqual(config["fieldCue"]["color"], "orange")
        self.assertEqual(config["fieldCue"]["absenceMeaning"], "UNKNOWN_NOT_CLOSED")
        self.assertFalse(config["capture"]["wholeDayVideoRetentionPermitted"])
        self.assertFalse(config["boundary"]["gateStateInferred"])

    def test_02_media_url_and_capture_limits_fail_closed(self) -> None:
        valid = "https://manifest.googlevideo.com/api/manifest/hls_playlist/test.m3u8?expire=1"
        self.assertEqual(capture.validate_media_url(valid), valid)
        with self.assertRaises(capture.LiveCaptureError):
            capture.validate_media_url("http://manifest.googlevideo.com/test")
        with self.assertRaises(capture.LiveCaptureError):
            capture.validate_media_url("https://example.com/test.m3u8")
        with self.assertRaises(capture.LiveCaptureError):
            capture.ffmpeg_command("ffmpeg", valid, Path("frame-%06d.jpg"), 901, 2.0)
        with self.assertRaises(capture.LiveCaptureError):
            capture.ffmpeg_command("ffmpeg", valid, Path("frame-%06d.jpg"), 60, 8.0)

    def test_03_resolver_requires_one_allowlisted_combined_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            resolver = Path(temporary) / "fake-yt-dlp"
            resolver.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'https://manifest.googlevideo.com/test.m3u8?token=secret'\n",
                encoding="utf-8",
            )
            resolver.chmod(resolver.stat().st_mode | stat.S_IXUSR)
            resolved = capture.resolve_media_url("https://www.youtube.com/watch?v=8_77np7-EDU", str(resolver), 720)
            self.assertTrue(resolved.startswith("https://manifest.googlevideo.com/"))

    def test_04_bounded_capture_is_atomic_and_does_not_store_signed_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = root / "fake-yt-dlp"
            resolver.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'https://manifest.googlevideo.com/test.m3u8?token=secret'\n",
                encoding="utf-8",
            )
            resolver.chmod(resolver.stat().st_mode | stat.S_IXUSR)
            ffmpeg = root / "fake-ffmpeg"
            ffmpeg.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from PIL import Image\n"
                "pattern = Path(sys.argv[-1])\n"
                "pattern.parent.mkdir(parents=True, exist_ok=True)\n"
                "for index in range(1, 4):\n"
                "    Image.new('RGB', (640, 360), (index * 20, 30, 40)).save(str(pattern).replace('%06d', f'{index:06d}'))\n",
                encoding="utf-8",
            )
            ffmpeg.chmod(ffmpeg.stat().st_mode | stat.S_IXUSR)
            output = root / "capture"
            report = capture.capture(
                output,
                duration_seconds=30,
                yt_dlp=str(resolver),
                ffmpeg=str(ffmpeg),
            )
            self.assertEqual(report["status"], capture.STATUS)
            self.assertEqual(report["capture"]["frameCount"], 3)
            self.assertFalse(report["source"]["resolvedMediaUrlStored"])
            self.assertTrue((output / "contact-sheet.jpg").is_file())
            self.assertEqual(report["review"]["contactSheet"]["tileCount"], 3)
            saved = json.loads((output / "capture.json").read_text(encoding="utf-8"))
            self.assertNotIn("token=secret", (output / "capture.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["boundary"]["targetBarrageIntervalSelected"])
            self.assertFalse(saved["boundary"]["gateStateInferred"])
            with self.assertRaises(capture.LiveCaptureError):
                capture.capture(output, duration_seconds=30, yt_dlp=str(resolver), ffmpeg=str(ffmpeg))


if __name__ == "__main__":
    unittest.main()
