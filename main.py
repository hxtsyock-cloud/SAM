import os
from typing import List, Optional, Tuple
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from platforms import tiktok, snapchat, instagram, twitter, facebook, youtube
from utils.cache import cache_get, cache_set
from utils.quality import normalize_quality, quality_options
from utils.rate_limit import rate_limit

app = FastAPI(title="Video Downloader Backend")

PLATFORMS = {
    "tiktok": tiktok,
    "snapchat": snapchat,
    "instagram": instagram,
    "twitter": twitter,
    "x": twitter,       # alias يطابق x.com
    "facebook": facebook,
    "youtube": youtube,
}


def _canonical_platform(platform: str) -> str:
    return "twitter" if platform == "x" else platform


def _find_platform(video_url: str) -> Optional[Tuple[str, object]]:
    url_lower = video_url.lower()

    for name, module in PLATFORMS.items():
        if hasattr(module, "matches_url") and module.matches_url(video_url):
            return name, module

    # كشف احتياطي بالاسم، مع تجاهل alias "x" حتى لا يطابق روابط عشوائية.
    for name, module in PLATFORMS.items():
        if name != "x" and name in url_lower:
            return name, module

    return None


def _validated_quality(quality: str, platform: str) -> str:
    try:
        return normalize_quality(quality, _canonical_platform(platform))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/platforms")
async def get_platforms():
    return {
        "platforms": list(PLATFORMS.keys()),
        "qualities": {
            platform: quality_options(_canonical_platform(platform))
            for platform in PLATFORMS
        },
    }


@app.post("/download/by-url")
async def download_by_url(
    request: Request,
    video_url: str,
    quality: str = "best",
):
    rate_limit(request)
    matched = _find_platform(video_url)
    if not matched:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    platform, module = matched
    selected_quality = _validated_quality(quality, platform)
    cache_key = f"{video_url}|quality={selected_quality}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    result = module.download_by_url(video_url, quality=selected_quality)
    cache_set(cache_key, result)
    return result


@app.post("/download/by-username")
async def download_by_username(
    request: Request,
    platform: str,
    username: str,
    quality: str = "best",
):
    rate_limit(request)
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    selected_quality = _validated_quality(quality, platform)
    return PLATFORMS[platform].download_by_username(
        username,
        quality=selected_quality,
    )


@app.post("/download/by-ids")
async def download_by_ids(
    request: Request,
    platform: str,
    video_ids: List[str],
    quality: str = "best",
):
    rate_limit(request)
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    selected_quality = _validated_quality(quality, platform)
    return PLATFORMS[platform].download_by_ids(
        video_ids,
        quality=selected_quality,
    )


@app.get("/download/file")
async def download_file(filename: str):
    # حماية: نأخذ اسم الملف فقط بدون أي مسار مجلدات،
    # عشان نمنع أي شخص يحاول يوصل لملفات ثانية بالسيرفر
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(os.getcwd(), safe_filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/octet-stream",
    )
