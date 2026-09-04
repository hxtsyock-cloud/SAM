import yt_dlp
from typing import Dict

def matches_url(video_url: str) -> bool:
    return "facebook.com" in video_url or "fb.watch" in video_url

def download_by_url(video_url: str) -> Dict:
    ydl_opts = {"format": "best", "outtmpl": "%(id)s.%(ext)s"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "facebook",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "filepath": ydl.prepare_filename(info),
        }
