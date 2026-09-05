import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from platforms import facebook, instagram, snapchat, tiktok, twitter, youtube
from utils.cache import cache_get, cache_set
from utils.media import (
    AUDIO_FORMATS,
    MEDIA_MODES,
    download_media,
    id_to_url,
    inspect_media,
    normalize_audio_format,
    normalize_compression_crf,
    normalize_mode,
    profile_url,
)
from utils.quality import normalize_quality, quality_options
from utils.rate_limit import rate_limit

app = FastAPI(title="Video Downloader Backend")

PLATFORMS = {
    "tiktok": tiktok,
    "snapchat": snapchat,
    "instagram": instagram,
    "twitter": twitter,
    "x": twitter,
    "facebook": facebook,
    "youtube": youtube,
}


class SelectedDownloadRequest(BaseModel):
    video_urls: List[str]
    quality: str = "best"
    mode: str = "video"
    audio_format: str = "m4a"
    compress: bool = False
    compression_crf: int = 28


def _canonical_platform(platform: str) -> str:
    return "twitter" if platform == "x" else platform


def _find_platform(video_url: str) -> Optional[Tuple[str, object]]:
    url_lower = video_url.lower()
    for name, module in PLATFORMS.items():
        if hasattr(module, "matches_url") and module.matches_url(video_url):
            return _canonical_platform(name), module

    for name, module in PLATFORMS.items():
        if name != "x" and name in url_lower:
            return _canonical_platform(name), module
    return None


def _platform_or_error(video_url: str) -> str:
    matched = _find_platform(video_url)
    if not matched:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    return matched[0]


def _options(
    platform: str,
    quality: str,
    mode: str,
    audio_format: str,
    compress: bool,
    compression_crf: int,
) -> Dict[str, Any]:
    try:
        return {
            "quality": normalize_quality(quality, platform),
            "mode": normalize_mode(mode),
            "audio_format": normalize_audio_format(audio_format),
            "compress": bool(compress),
            "compression_crf": normalize_compression_crf(compression_crf),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _media_error(exc: Exception) -> None:
    message = str(exc)
    if message.startswith("Selection required"):
        raise HTTPException(status_code=409, detail=message) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=503, detail=message) from exc
    raise HTTPException(status_code=400, detail=message) from exc


def _capabilities() -> Dict[str, Any]:
    return {
        "platforms": list(PLATFORMS.keys()),
        "qualities": {
            platform: quality_options(_canonical_platform(platform))
            for platform in PLATFORMS
        },
        "modes": list(MEDIA_MODES),
        "audio_formats": list(AUDIO_FORMATS),
        "features": {
            "profile_inspection": True,
            "playlist_selection_before_download": True,
            "story_inspection": True,
            "finished_live_download": True,
            "gif_conversion": True,
            "video_compression": True,
            "download_all_profile_videos": True,
            "watermark_removal": False,
            "watermark_policy": "original-source-only when exposed by the platform",
        },
        "frontend_inputs": ["video_or_story_url", "username"],
    }


def _inspect_source(source_url: str, limit: int = 100) -> Dict[str, Any]:
    platform = _platform_or_error(source_url)
    try:
        return inspect_media(source_url, platform, limit=max(0, min(limit, 1000)))
    except (ValueError, RuntimeError) as exc:
        _media_error(exc)
    raise AssertionError("unreachable")


def _download_one(
    request: Request,
    source_url: str,
    quality: str,
    mode: str,
    audio_format: str,
    compress: bool,
    compression_crf: int,
) -> Dict[str, Any]:
    rate_limit(request)
    platform = _platform_or_error(source_url)
    options = _options(
        platform,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
    )
    cache_key = "|".join(
        [
            source_url,
            options["quality"],
            options["mode"],
            options["audio_format"],
            str(options["compress"]),
            str(options["compression_crf"]),
        ]
    )
    if options["mode"] == "video" and not options["compress"]:
        cached = cache_get(cache_key)
        if cached:
            return cached

    try:
        result = download_media(source_url, platform, **options)
    except (ValueError, RuntimeError) as exc:
        _media_error(exc)
    if options["mode"] == "video" and not options["compress"]:
        cache_set(cache_key, result)
    return result


def _entry_urls(profile: Dict[str, Any]) -> List[str]:
    urls = []
    for entry in profile.get("entries", []):
        url = entry.get("webpage_url") or entry.get("url")
        if url:
            urls.append(url)
    return urls


def _download_many(
    request: Request,
    video_urls: List[str],
    quality: str,
    mode: str,
    audio_format: str,
    compress: bool,
    compression_crf: int,
) -> Dict[str, Any]:
    if not video_urls:
        raise HTTPException(status_code=400, detail="video_urls cannot be empty")

    videos = []
    errors = []
    for source_url in video_urls:
        try:
            videos.append(
                _download_one(
                    request,
                    source_url,
                    quality,
                    mode,
                    audio_format,
                    compress,
                    compression_crf,
                )
            )
        except HTTPException as exc:
            errors.append({"url": source_url, "error": exc.detail})
    return {
        "requested": len(video_urls),
        "downloaded": len(videos),
        "videos": videos,
        "errors": errors,
    }


@app.get("/platforms")
async def get_platforms():
    return _capabilities()


@app.get("/capabilities")
async def get_capabilities():
    return _capabilities()


@app.get("/inspect/by-url")
async def inspect_by_url(video_url: str, limit: int = 100):
    return _inspect_source(video_url, limit)


@app.get("/inspect/playlist")
async def inspect_playlist(playlist_url: str, limit: int = 100):
    return _inspect_source(playlist_url, limit)


@app.get("/inspect/story")
async def inspect_story(story_url: str, limit: int = 100):
    return _inspect_source(story_url, limit)


@app.post("/inspect/by-username")
async def inspect_by_username(
    request: Request,
    platform: str,
    username: str,
    limit: int = 100,
):
    rate_limit(request)
    platform = _canonical_platform(platform.lower())
    if platform not in PLATFORMS or platform == "x":
        raise HTTPException(status_code=400, detail="Unsupported platform")
    try:
        source_url = profile_url(platform, username)
        result = inspect_media(source_url, platform, limit=max(0, min(limit, 1000)))
        result["profile_url"] = source_url
        result["username"] = username.lstrip("@")
        return result
    except (ValueError, RuntimeError) as exc:
        _media_error(exc)


@app.post("/download/by-url")
async def download_by_url(
    request: Request,
    video_url: str,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
):
    return _download_one(
        request,
        video_url,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
    )


@app.post("/download/live")
async def download_finished_live(
    request: Request,
    video_url: str,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
):
    return _download_one(
        request,
        video_url,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
    )


@app.post("/download/selected")
async def download_selected(request: Request, payload: SelectedDownloadRequest):
    return _download_many(
        request,
        payload.video_urls,
        payload.quality,
        payload.mode,
        payload.audio_format,
        payload.compress,
        payload.compression_crf,
    )


@app.post("/download/by-username")
async def download_by_username(
    request: Request,
    platform: str,
    username: str,
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
    download_all: bool = False,
    limit: int = 1000,
):
    rate_limit(request)
    canonical = _canonical_platform(platform.lower())
    if canonical not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    try:
        source_url = profile_url(canonical, username)
        profile = inspect_media(source_url, canonical, limit=max(0, min(limit, 10000)))
        profile["profile_url"] = source_url
        profile["username"] = username.lstrip("@")
    except (ValueError, RuntimeError) as exc:
        _media_error(exc)

    if not download_all:
        profile["selection_required"] = True
        return profile

    urls = _entry_urls(profile)
    return _download_many(
        request,
        urls,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
    )


@app.post("/download/by-ids")
async def download_by_ids(
    request: Request,
    platform: str,
    video_ids: List[str],
    quality: str = "best",
    mode: str = "video",
    audio_format: str = "m4a",
    compress: bool = False,
    compression_crf: int = 28,
):
    canonical = _canonical_platform(platform.lower())
    if canonical not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    try:
        urls = [id_to_url(canonical, video_id) for video_id in video_ids]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _download_many(
        request,
        urls,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
    )


@app.get("/download/file")
async def download_file(filename: str):
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(os.getcwd(), safe_filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/octet-stream",
    )
