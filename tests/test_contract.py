import unittest

from utils.media import (
    AUDIO_FORMATS,
    MEDIA_MODES,
    build_ydl_options,
    normalize_audio_format,
    normalize_compression_crf,
    normalize_limit,
    normalize_mode,
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


if __name__ == "__main__":
    unittest.main()