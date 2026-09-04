import os
from typing import List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from platforms import tiktok, snapchat, instagram, twitter, facebook, youtube
from utils.cache import cache_get, cache_set
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

@app.get("/platforms")
async def get_platforms():
    return {"platforms": list(PLATFORMS.keys())}

@app.post("/download/by-url")
async def download_by_url(request: Request, video_url: str):
    rate_limit(request)
    cached = cache_get(video_url)
    if cached:
        return cached

    # أولاً: تحقق إن أي موديول يوفر matches_url
    for name, module in PLATFORMS.items():
        if hasattr(module, "matches_url") and module.matches_url(video_url):
            result = module.download_by_url(video_url)
            cache_set(video_url, result)
            return result

    # ثانياً: كشف بسيط بالاسم داخل الرابط
    for name, module in PLATFORMS.items():
        if name in video_url:
            result = module.download_by_url(video_url)
            cache_set(video_url, result)
            return result

    raise HTTPException(status_code=400, detail="Unsupported platform")

@app.post("/download/by-username")
async def download_by_username(request: Request, platform: str, username: str):
    rate_limit(request)
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    return PLATFORMS[platform].download_by_username(username)

@app.post("/download/by-ids")
async def download_by_ids(request: Request, platform: str, video_ids: List[str]):
    rate_limit(request)
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    return PLATFORMS[platform].download_by_ids(video_ids)

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
