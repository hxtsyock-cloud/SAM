import yt_dlp
from typing import List, Dict

def matches_url(video_url: str) -> bool:
    return "youtube.com" in video_url or "youtu.be" in video_url

def download_by_url(video_url: str) -> Dict:
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "%(id)s.%(ext)s",
        "cookiefile": "/etc/secrets/youtube_cookies.txt",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "youtube",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "ext": info.get("ext"),
            "filepath": ydl.prepare_filename(info),
        }

def download_by_username(username: str) -> Dict:
    # yt-dlp يدعم قنوات يوتيوب
    url = f"https://www.youtube.com/@{username}"
    return download_by_url(url)

def download_by_ids(video_ids: List[str]) -> Dict:
    results = []
    for vid in video_ids:
        url = f"https://youtube.com/watch?v={vid}"
        results.append(download_by_url(url))
    return {"platform": "youtube", "videos": results}
