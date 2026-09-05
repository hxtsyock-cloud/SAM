from typing import Dict, List, Optional

QUALITY_HEIGHTS: Dict[str, int] = {
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
    "4320p": 4320,
}

QUALITY_ALIASES = {
    "144": "144p",
    "240": "240p",
    "360": "360p",
    "480": "480p",
    "720": "720p",
    "1080": "1080p",
    "1440": "1440p",
    "2160": "2160p",
    "4320": "4320p",
    "4k": "2160p",
    "8k": "4320p",
}

PLATFORM_MAX_HEIGHTS: Dict[str, int] = {
    "youtube": 4320,
    "tiktok": 2160,
    "snapchat": 2160,
    "instagram": 2160,
    "twitter": 2160,
    "facebook": 2160,
}


def normalize_quality(quality: Optional[str], platform: str) -> str:
    value = (quality or "best").strip().lower()
    value = QUALITY_ALIASES.get(value, value)

    if value == "best":
        return value
    if value not in QUALITY_HEIGHTS:
        choices = ", ".join(["best", *QUALITY_HEIGHTS.keys()])
        raise ValueError(f"Invalid quality. Choose one of: {choices}")

    max_height = PLATFORM_MAX_HEIGHTS.get(platform, 2160)
    if QUALITY_HEIGHTS[value] > max_height:
        raise ValueError(
            f"{platform} supports up to {max_height}p. Requested quality: {value}"
        )
    return value


def format_selector(quality: Optional[str], platform: str) -> str:
    selected_quality = normalize_quality(quality, platform)
    if selected_quality == "best":
        return "bestvideo+bestaudio/best"

    height = QUALITY_HEIGHTS[selected_quality]
    return (
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]"
    )


def quality_options(platform: str) -> List[str]:
    max_height = PLATFORM_MAX_HEIGHTS.get(platform, 2160)
    return [
        "best",
        *[
            quality
            for quality, height in QUALITY_HEIGHTS.items()
            if height <= max_height
        ],
    ]
