import os
import json
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from yt_dlp.utils import DownloadError

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
    normalize_limit,
    normalize_mode,
    profile_url,
)
from utils.quality import normalize_quality, quality_options
from utils.rate_limit import rate_limit

# === تعديل جديد: استيراد دوال تشغيل/إيقاف خادم PO Token + دالة التشخيص ===
from pot_provider import start_pot_server, stop_pot_server, get_pot_status

app = FastAPI(title="Video Downloader Backend")

# === تعديل جديد: تشغيل خادم POT عند إقلاع التطبيق، وإيقافه عند إغلاقه ===
@app.on_event("startup")
async def _startup_pot_server():
    success = start_pot_server()
    if not success:
        # التطبيق يستمر يشتغل حتى لو فشل — باقي المنصات ما تعتمد على هذا الخادم،
        # بس يوتيوب غالبًا بيفشل لين تُحل المشكلة. نسجل تحذير واضح باللوق.
        print(
            "WARNING: PO Token server failed to start — YouTube downloads will "
            "likely fail until this is fixed. Other platforms are unaffected."
        )


@app.on_event("shutdown")
async def _shutdown_pot_server():
    stop_pot_server()


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
    no_watermark: bool = False
    max_concurrency: int = 4


def _normalize_download_filename(filename: str) -> str:
    """Accept a filepath or a serialized API result without exposing paths."""
    candidate = filename
    for _ in range(2):
        candidate = unquote(candidate)

    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        payload = None

    if isinstance(payload, dict):
        candidate = payload.get("filepath") or payload.get("filename") or ""
    elif isinstance(payload, str):
        candidate = payload

    for _ in range(2):
        candidate = unquote(str(candidate))
    candidate = os.path.basename(candidate)
    if not candidate or candidate in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required")
    return candidate


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
    no_watermark: bool = False,
) -> Dict[str, Any]:
    try:
        return {
            "quality": normalize_quality(quality, platform),
            "mode": normalize_mode(mode),
            "audio_format": normalize_audio_format(audio_format),
            "compress": bool(compress),
            "compression_crf": normalize_compression_crf(compression_crf),
            "no_watermark": bool(no_watermark),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _media_error(exc: Exception) -> None:
    message = str(exc).strip()
    lowered = message.lower()
    if message.startswith("Selection required"):
        raise HTTPException(status_code=409, detail=message) from exc
    if isinstance(exc, DownloadError):
        requires_auth = any(
            phrase in lowered
            for phrase in (
                "sign in",
                "log in",
                "login",
                "not a bot",
                "cookies",
                "authentication",
                "confirm you're not a bot",
            )
        )
        if requires_auth:
            message = (
                "The platform requires authentication cookies. Configure the "
                "matching platform cookie secret, for example "
                "INSTAGRAM_COOKIES_B64 or YOUTUBE_COOKIES_B64 using a Netscape "
                "cookies file, then retry."
            )
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_extractor_error", "message": message[:500]},
        ) from exc
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
            "watermark_free_strict_mode": True,
            "watermark_policy": (
                "no_watermark=true returns only an explicitly verified "
                "watermark-free source; otherwise it fails safely"
            ),
            "parallel_batch_download": True,
        },
        "frontend_inputs": ["video_or_story_url", "username"],
    }


def _inspect_source(
    source_url: str,
    limit: int = 100,
    source_kind: str = "video",
) -> Dict[str, Any]:
    platform = _platform_or_error(source_url)
    try:
        return inspect_media(
            source_url,
            platform,
            limit=normalize_limit(limit),
            source_kind=source_kind,
        )
    except (ValueError, RuntimeError, DownloadError) as exc:
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
    no_watermark: bool = False,
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
        no_watermark,
    )
    cache_key = "|".join(
        [
            source_url,
            options["quality"],
            options["mode"],
            options["audio_format"],
            str(options["compress"]),
            str(options["compression_crf"]),
            str(options["no_watermark"]),
        ]
    )
    if options["mode"] == "video" and not options["compress"]:
        cached = cache_get(cache_key)
        if cached:
            return cached

    try:
        result = download_media(source_url, platform, **options)
    except (ValueError, RuntimeError, DownloadError) as exc:
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
    no_watermark: bool = False,
    max_concurrency: int = 4,
) -> Dict[str, Any]:
    if not video_urls:
        raise HTTPException(status_code=400, detail="video_urls cannot be empty")

    try:
        workers = max(1, min(int(max_concurrency), 8))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="max_concurrency must be an integer from 1 to 8",
        ) from exc

    videos_by_index: Dict[int, Dict[str, Any]] = {}
    errors_by_index: Dict[int, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _download_one,
                request,
                source_url,
                quality,
                mode,
                audio_format,
                compress,
                compression_crf,
                no_watermark,
            ): (index, source_url)
            for index, source_url in enumerate(video_urls)
        }
        for future in as_completed(futures):
            index, source_url = futures[future]
            try:
                videos_by_index[index] = future.result()
            except HTTPException as exc:
                errors_by_index[index] = {"url": source_url, "error": exc.detail}
            except Exception as exc:
                errors_by_index[index] = {
                    "url": source_url,
                    "error": {"code": "unexpected_download_error", "message": str(exc)},
                }

    videos = [videos_by_index[index] for index in sorted(videos_by_index)]
    errors = [errors_by_index[index] for index in sorted(errors_by_index)]
    return {
        "requested": len(video_urls),
        "downloaded": len(videos),
        "videos": videos,
        "errors": errors,
    }


@app.get("/platforms")
async def get_platforms():
    return _capabilities()


@app.get("/")
async def health():
    return {
        "service": app.title,
        "status": "ok",
        "health": "/",
        "documentation": "/docs",
        "capabilities": "/capabilities",
    }


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/capabilities")
async def get_capabilities():
    return _capabilities()


# === تعديل جديد: Endpoint تشخيصي مؤقت لفحص حالة خادم POT من داخل نفس العملية ===
@app.get("/debug/pot-status")
async def debug_pot_status():
    return get_pot_status()


# === تعديل جديد: Endpoint تشخيصي لالتقاط سجل yt-dlp الكامل عند فحص فيديو يوتيوب ===
@app.get("/debug/youtube-probe")
async def debug_youtube_probe_endpoint(video_url: str):
    from utils.media import debug_youtube_probe
    return debug_youtube_probe(video_url)


# === تعديل جديد: Endpoint تشخيصي يرجّع الرابط المباشر بدون تحميل على السيرفر ===
@app.get("/debug/youtube-direct-link")
async def debug_youtube_direct_link_endpoint(video_url: str):
    from utils.media import debug_youtube_direct_link
    return debug_youtube_direct_link(video_url)


# === تعديل جديد: Endpoint تشخيصي سريع لحالة JS runtime (deno) بدون اتصال بيوتيوب ===
@app.get("/debug/youtube-js-runtime")
async def debug_youtube_js_runtime_endpoint():
    from utils.media import debug_youtube_js_runtime_status
    return debug_youtube_js_runtime_status()


@app.get("/inspect/by-url")
async def inspect_by_url(video_url: str, limit: int = 100):
    return _inspect_source(video_url, limit)


@app.get("/inspect/playlist")
async def inspect_playlist(playlist_url: str, limit: int = 100):
    return _inspect_source(playlist_url, limit, source_kind="playlist")


@app.get("/inspect/story")
async def inspect_story(story_url: str, limit: int = 100):
    return _inspect_source(story_url, limit, source_kind="story")


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
        result = inspect_media(
            source_url,
            platform,
            limit=normalize_limit(limit),
            source_kind="profile",
            maximum=1000,
        )
        result["profile_url"] = source_url
        result["username"] = username.lstrip("@")
        return result
    except (ValueError, RuntimeError, DownloadError) as exc:
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
    no_watermark: bool = False,
):
    return _download_one(
        request,
        video_url,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
        no_watermark,
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
    no_watermark: bool = False,
):
    return _download_one(
        request,
        video_url,
        quality,
        mode,
        audio_format,
        compress,
        compression_crf,
        no_watermark,
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
        payload.no_watermark,
        payload.max_concurrency,
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
    no_watermark: bool = False,
    max_concurrency: int = 4,
):
    rate_limit(request)
    canonical = _canonical_platform(platform.lower())
    if canonical not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    try:
        source_url = profile_url(canonical, username)
        profile = inspect_media(
            source_url,
            canonical,
            limit=normalize_limit(limit, maximum=10000),
            source_kind="profile",
            maximum=10000,
        )
        profile["profile_url"] = source_url
        profile["username"] = username.lstrip("@")
    except (ValueError, RuntimeError, DownloadError) as exc:
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
        no_watermark,
        max_concurrency,
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
    no_watermark: bool = False,
    max_concurrency: int = 4,
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
        no_watermark,
        max_concurrency,
    )


@app.get("/download/file")
async def download_file(filename: str):
    safe_filename = _normalize_download_filename(filename)
    file_path = os.path.join(os.getcwd(), safe_filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/octet-stream",
    )
