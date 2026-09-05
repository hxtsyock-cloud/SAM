import unittest

from utils.media import (
    AUDIO_FORMATS,
    MEDIA_MODES,
    build_ydl_options,
    _final_filepath,
    normalize_audio_format,
    normalize_compression_crf,
    normalize_limit,
    normalize_mode,
    _watermark_is_proven_absent,
)
from utils.quality import format_selector, normalize_quality


PLATFORMS = ("youtube", "tiktok", "snapchat", "instagram", "twitter", "facebook")


class MediaContractTests(unittest.TestCase):
    def test_quality_limits(self):
        for platform in PLATFORMS:
            self.assertEqual(normalize_quality("4k", platform), "2160p")
            if platform == "youtube":
                self.assertEqual(normalize_quality("8k", platform), "4320p")
            else:
                with self.assertRaises(ValueError):
                    normalize_quality("8k", platform)

    def test_audio_formats_and_modes(self):
        for audio_format in AUDIO_FORMATS:
            self.assertEqual(normalize_audio_format(audio_format), audio_format)
        for mode in MEDIA_MODES:
            self.assertEqual(normalize_mode(mode), mode)

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_audio_format("flac")
        with self.assertRaises(ValueError):
            normalize_mode("unknown")
        with self.assertRaises(ValueError):
            normalize_compression_crf(17)
        with self.assertRaises(ValueError):
            normalize_compression_crf(41)
        with self.assertRaises(ValueError):
            normalize_limit(0)

    def test_format_selectors_are_bounded(self):
        for platform in PLATFORMS:
            selector = format_selector("4k", platform)
            self.assertIn("height<=2160", selector)

    def test_all_media_modes_build_options(self):
        for platform in PLATFORMS:
            for mode in MEDIA_MODES:
                options = build_ydl_options(
                    platform,
                    quality="4k",
                    mode=mode,
                    audio_format="mp3",
                )
                self.assertTrue(options["noplaylist"])
                self.assertIn("format", options)
                if mode in ("video", "video_no_audio"):
                    self.assertEqual(
                        options["postprocessors"][0]["key"],
                        "FFmpegVideoRemuxer",
                    )

    def test_video_outputs_are_mp4(self):
        self.assertEqual(
            _final_filepath("abc.webm", "video", "m4a", False),
            "abc.mp4",
        )
        self.assertEqual(
            _final_filepath("abc.mkv", "video_no_audio", "m4a", False),
            "abc.mp4",
        )

    def test_watermark_mode_fails_closed(self):
        self.assertTrue(_watermark_is_proven_absent({"watermark_free": True}))
        self.assertTrue(_watermark_is_proven_absent({"has_watermark": False}))
        self.assertFalse(_watermark_is_proven_absent({}))


if __name__ == "__main__":
    unittest.main()