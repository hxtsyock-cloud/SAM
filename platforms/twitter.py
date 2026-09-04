import yt_dlp
from typing import List, Dict

def matches_url(video_url: str) -> bool:
    return any(domain in video_url for domain in ("twitter.com", "x.com", "t.co"))

def download_by_url(video_url: str) -> Dict:
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "%(id)s.%(ext)s",  # اسم الملف الناتج
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "twitter",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "ext": info.get("ext"),
            "filepath": ydl.prepare_filename(info),
        }

def download_by_username(username: str) -> Dict:
    # تويتر/X لا يدعم مباشرةً تنزيل كل فيديوهات مستخدم عبر yt-dlp
    # تحتاج API أو روابط مباشرة. هنا نرجع رسالة توضيحية.
    return {"platform": "twitter", "username": username, "error": "Not supported directly"}

def download_by_ids(video_ids: List[str]) -> Dict:
    results = []
    for vid in video_ids:
        url = f"https://twitter.com/i/status/{vid}"
        results.append(download_by_url(url))
    return {"platform": "twitter", "videos": results}
