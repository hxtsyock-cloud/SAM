import base64
import os
import shutil
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from utils.quality import format_selector, normalize_quality

AUDIO_FORMATS = ("mp3", "aac", "m4a", "wav")
MEDIA_MODES = ("video", "audio", "video_no_audio", "gif")
MAX_PROFILE_LIMIT = 1000
MODE_ALIASES = {
    "audio_only": "audio",
    "audio-only": "audio",
    "video_only": "video_no_audio",
    "video-only": "video_no_audio",
    "video_without_audio": "video_no_audio",
    "video-without-audio": "video_no_audio",
    "no_audio": "video_no_audio",
    "mute": "video_no_audio",
    "animated_gif": "gif",
}


def normalize_limit(limit: int, maximum: int = MAX_PROFILE_LIMIT) -> int:
    """Validate collection limits instead of treating negative values as unlimited."""
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a positive integer") from exc
    if value < 1:
        raise ValueError("limit must be at least 1")
    return min(value, maximum)


def normalize_mode(mode: Optional[str]) -> str:
    value = (mode or "video").strip().lower()
    value = MODE_ALIASES.get(value, value)
    if value not in MEDIA_MODES:
        choices = ", ".join(MEDIA_MODES)
        raise ValueError(f"Invalid mode. Choose one of: {choices}")
    return value


def normalize_audio_format(audio_format: Optional[str]) -> str:
    value = (audio_format or "m4a").strip().lower().lstrip(".")
    if value not in AUDIO_FORMATS:
        choices = ", ".join(AUDIO_FORMATS)
        raise ValueError(f"Invalid audio_format. Choose one of: {choices}")
    return value


def normalize_compression_crf(crf: int) -> int:
    try:
        value = int(crf)
    except (TypeError, ValueError) as exc:
        raise ValueError("compression_crf must be an integer from 18 to 40") from exc
    if not 18 <= value <= 40:
        raise ValueError("compression_crf must be between 18 and 40")
    return value


def _ffmpeg_location(required: bool = False) -> Optional[str]:
    location = shutil.which("ffmpeg")
    if not location:
        try:
            import imageio_ffmpeg

            location = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            location = None
    if required and not location:
        raise RuntimeError(
            "FFmpeg is required for audio, GIF, and compression features"
        )
    return location


def _copy_cookie(source: str, destination: str) -> Optional[str]:
    if not os.path.exists(source):
        return None
    shutil.copy(source, destination)
    return destination


def _cookiefile(
    env_name: str,
    source: str,
    destination: str,
) -> Optional[str]:
    configured_path = os.getenv(f"{env_name}_PATH")
    if configured_path and os.path.exists(configured_path):
        shutil.copy(configured_path, destination)
        return destination

    encoded = os.getenv(f"{env_name}_B64")
    if encoded:
        try:
            cookie_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"{env_name}_B64 is not valid base64") from exc
        with open(destination, "wb") as cookie_file:
            cookie_file.write(cookie_bytes)
        return destination

    cookie_text = os.getenv(env_name)
    if cookie_text:
        with open(destination, "w", encoding="utf-8", newline="") as cookie_file:
            cookie_file.write(cookie_text)
        return destination

    return _copy_cookie(source, destination)


def _platform_options(platform: str) -> Dict[str, Any]:
    options: Dict[str, Any] = {}

    if platform == "facebook":
        cookiefile = _cookiefile(
            "FACEBOOK_COOKIES",
            "/etc/secrets/facebook_cookies.txt",
            "/tmp/facebook_cookies.txt",
        )
        if cookiefile:
            options["cookiefile"] = cookiefile

    if platform == "youtube":
        cookiefile = _cookiefile(
            "YOUTUBE_COOKIES",
            "/etc/secrets/youtube_cookies.txt",
            "/tmp/youtube_cookies.txt",
        )
        if cookiefile:
            options["cookiefile"] = cookiefile
        options["extractor_args"] = {
            "youtube": {"player_client": ["tv", "web"]}
        }
        if shutil.which("deno"):
            options["js_runtimes"] = {"deno": {}}
        options["remote_components"] = ["ejs:github"]

    if platform == "tiktok":
        options.update(
            {
                "impersonate": ImpersonateTarget.from_str("chrome"),
                "retries": 5,
                "fragment_retries": 5,
                "http_headers": {"Referer": "https://www.tiktok.com/"},
            }
        )

    return options


def build_ydl_options(
    platform: str,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
    noplaylist: bool = True,
    extract_flat: bool = False,
    no_watermark: bool = False,
    ensure_mp4: bool = True,
) -> Dict[str, Any]:
    selected_quality = normalize_quality(quality, platform)
    selected_mode = normalize_mode(mode)
    selected_audio_format = normalize_audio_format(audio_format)
    selected_crf = normalize_compression_crf(compression_crf)

    if compress and selected_mode in ("audio", "gif"):
        raise ValueError("Compression is available for video modes only")

    requires_ffmpeg = (
        selected_mode in ("audio", "gif")
        or compress
        or (ensure_mp4 and selected_mode in ("video", "video_no_audio"))
    )
    ffmpeg_location = _ffmpeg_location(required=requires_ffmpeg)
    include_audio = selected_mode == "video"

    if selected_mode == "audio":
        media_format = "bestaudio/best"
    else:
        media_format = format_selector(
            selected_quality,
            platform,
            include_audio=include_audio,
        )

    options: Dict[str, Any] = {
        "format": media_format,
        "outtmpl": "%(id)s.%(ext)s",
        "noplaylist": noplaylist,
        "quiet": True,
    }
    options.update(_platform_options(platform))
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    if extract_flat:
        options["extract_flat"] = True

    if selected_mode == "audio":
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": selected_audio_format,
            }
        ]
    elif selected_mode == "gif":
        options["postprocessors"] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": "gif"}
        ]
    elif compress:
        options["postprocessors"] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ]
        options["postprocessor_args"] = {
            "VideoConvertor": [
                "-c:v",
                "libx264",
                "-crf",
                str(selected_crf),
                "-preset",
                "slow",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ]
        }
    elif ensure_mp4 and selected_mode in ("video", "video_no_audio"):
        # Remuxing copies the encoded streams and therefore preserves their
        # quality.  It deliberately fails when the source codecs cannot be
        # placed in an MP4 container instead of silently transcoding them.
        options["postprocessors"] = [
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
        ]

    return options


def _entry_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    fields = (
        "id",
        "title",
        "description",
        "url",
        "webpage_url",
        "thumbnail",
        "duration",
        "upload_date",
        "timestamp",
        "view_count",
        "like_count",
        "comment_count",
        "is_live",
        "live_status",
        "uploader",
        "uploader_id",
        "channel",
        "channel_id",
        "repost_count",
        "is_repost",
    )
    return {key: entry.get(key) for key in fields if entry.get(key) is not None}


def serialize_info(
    info: Dict[str, Any],
    source_url: str,
    limit: int = 100,
    maximum: int = MAX_PROFILE_LIMIT,
) -> Dict[str, Any]:
    limit = normalize_limit(limit, maximum=maximum)
    raw_entries = info.get("entries") or []
    entries = list(raw_entries)
    total = len(entries)
    if limit > 0:
        entries = entries[:limit]

    fields = (
        "id",
        "title",
        "description",
        "webpage_url",
        "thumbnail",
        "duration",
        "upload_date",
        "timestamp",
        "view_count",
        "like_count",
        "comment_count",
        "uploader",
        "uploader_id",
        "channel",
        "channel_id",
        "channel_url",
        "categories",
        "tags",
        "age_limit",
        "availability",
        "is_live",
        "live_status",
        "release_timestamp",
    )
    result = {
        "source_url": source_url,
        "type": info.get("_type", "video"),
        "entry_count": total,
        "has_more": limit > 0 and total > len(entries),
        "entries": [_entry_summary(entry) for entry in entries if entry],
        "videos": [_entry_summary(entry) for entry in entries if entry],
        "profile": {
            "username": info.get("uploader") or info.get("uploader_id"),
            "display_name": info.get("uploader") or info.get("channel"),
            "avatar_url": (
                info.get("uploader_avatar")
                or info.get("channel_thumbnail")
                or info.get("thumbnail")
            ),
            "bio": info.get("uploader_description") or info.get("description"),
            "url": info.get("uploader_url") or info.get("channel_url"),
        },
        "reposts": info.get("reposts") or info.get("reposted_entries") or [],
        "reposts_available": bool(
            info.get("reposts") or info.get("reposted_entries")
        ),
    }
    result.update({key: info.get(key) for key in fields if info.get(key) is not None})
    return result


def inspect_media(
    source_url: str,
    platform: str,
    limit: int = 100,
    source_kind: str = "video",
    maximum: int = MAX_PROFILE_LIMIT,
) -> Dict[str, Any]:
    options = build_ydl_options(
        platform,
        mode="video",
        noplaylist=False,
        extract_flat=True,
        ensure_mp4=False,
    )
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(source_url, download=False)
    result = serialize_info(info, source_url, limit=limit, maximum=maximum)
    result["source_kind"] = source_kind
    return result


def _watermark_is_proven_absent(info: Dict[str, Any]) -> bool:
    """Only accept an explicit extractor guarantee for no-watermark mode."""
    if info.get("watermark_free") is True or info.get("is_watermark_free") is True:
        return True
    if info.get("has_watermark") is False or info.get("watermark") is False:
        return True
    for fmt in info.get("formats") or []:
        if fmt.get("watermark_free") is True or fmt.get("is_watermark_free") is True:
            return True
    return False


def _final_filepath(
    filename: str,
    mode: str,
    audio_format: str,
    compress: bool,
) -> str:
    root, _ = os.path.splitext(filename)
    if mode == "audio":
        return f"{root}.{audio_format}"
    if mode == "gif":
        return f"{root}.gif"
    if mode in ("video", "video_no_audio") or compress:
        return f"{root}.mp4"
    return filename


def download_media(
    source_url: str,
    platform: str,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
    no_watermark: bool = False,
) -> Dict[str, Any]:
    selected_mode = normalize_mode(mode)
    selected_audio_format = normalize_audio_format(audio_format)
    selected_crf = normalize_compression_crf(compression_crf)
    selected_quality = normalize_quality(quality, platform)

    probe_options = build_ydl_options(
        platform,
        quality=selected_quality,
        mode=selected_mode,
        audio_format=selected_audio_format,
        compress=compress,
        compression_crf=selected_crf,
        noplaylist=False,
        no_watermark=no_watermark,
    )
    with yt_dlp.YoutubeDL(probe_options) as ydl:
        info = ydl.extract_info(source_url, download=False)

    entries = list(info.get("entries") or [])
    if info.get("_type") in ("playlist", "multi_video") or len(entries) > 1:
        raise ValueError(
            "Selection required: inspect the source first and send selected video URLs"
        )

    live_status = info.get("live_status")
    if live_status == "is_live" or (
        info.get("is_live") is True
        and live_status not in {"was_live", "post_live", "not_live"}
    ):
        raise ValueError("The live stream is still in progress")
    if no_watermark and not _watermark_is_proven_absent(info):
        raise RuntimeError(
            "No watermark-free source was verified; refusing to return a "
            "possibly watermarked file"
        )

    download_options = build_ydl_options(
        platform,
        quality=selected_quality,
        mode=selected_mode,
        audio_format=selected_audio_format,
        compress=compress,
        compression_crf=selected_crf,
        noplaylist=True,
        no_watermark=no_watermark,
    )
    with yt_dlp.YoutubeDL(download_options) as ydl:
        ydl.download([source_url])
        filename = ydl.prepare_filename(info)

    filepath = _final_filepath(
        filename,
        selected_mode,
        selected_audio_format,
        compress,
    )
    if selected_mode in ("video", "video_no_audio") and not filepath.lower().endswith(
        ".mp4"
    ):
        raise RuntimeError("The downloaded video was not produced as an MP4 file")
    if not os.path.isfile(filepath):
        raise RuntimeError(f"Download completed but output file is missing: {filepath}")

    return {
        "platform": platform,
        "video_id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or source_url,
        "quality": selected_quality,
        "mode": selected_mode,
        "audio_format": selected_audio_format if selected_mode == "audio" else None,
        "compressed": bool(compress),
        "container": "mp4" if selected_mode in ("video", "video_no_audio") else None,
        "filepath": filepath,
    }


def profile_url(platform: str, username: str) -> str:
    value = username.strip().lstrip("@")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    encoded = quote(value, safe="._-")
    templates = {
        "youtube": f"https://www.youtube.com/@{encoded}",
        "tiktok": f"https://www.tiktok.com/@{encoded}",
        "instagram": f"https://www.instagram.com/{encoded}/",
        "twitter": f"https://x.com/{encoded}",
        "facebook": f"https://www.facebook.com/{encoded}",
        "snapchat": f"https://www.snapchat.com/add/{encoded}",
    }
    if platform not in templates:
        raise ValueError(f"Username lookup is not configured for {platform}")
    return templates[platform]


def id_to_url(platform: str, video_id: str) -> str:
    encoded = quote(str(video_id), safe="._-")
    templates = {
        "youtube": f"https://youtube.com/watch?v={encoded}",
        "tiktok": f"https://www.tiktok.com/@_/video/{encoded}",
        "twitter": f"https://twitter.com/i/status/{encoded}",
    }
    if platform not in templates:
        raise ValueError(
            "ID downloads are supported for youtube, tiktok, and twitter; "
            "use selected video URLs for other platforms"
        )
    return templates[platform]
