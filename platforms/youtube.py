import os
import shutil
from typing import List, Dict

import yt_dlp

from utils.quality import format_selector


def matches_url(video_url: str) -> bool:
    return "youtube.com" in video_url or "youtu.be" in video_url


def download_by_url(video_url: str, quality: str = "best") -> Dict:
    source_cookies = "/etc/secrets/youtube_cookies.txt"
    writable_cookies = "/tmp/youtube_cookies.txt"

    if os.path.exists(source_cookies):
        shutil.copy(source_cookies, writable_cookies)

    ydl_opts = {
        "format": format_selector(quality, "youtube"),
        "outtmpl": "%(id)s.%(ext)s",
        "cookiefile": writable_cookies,
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "web"],
            }
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "youtube",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "ext": info.get("ext"),
            "quality": quality,
            "filepath": ydl.prepare_filename(info),
        }


def download_by_username(username: str, quality: str = "best") -> Dict:
    url = f"https://www.youtube.com/@{username}"
    return download_by_url(url, quality=quality)


def download_by_ids(video_ids: List[str], quality: str = "best") -> Dict:
    results = []
    for vid in video_ids:
        url = f"https://youtube.com/watch?v={vid}"
        results.append(download_by_url(url, quality=quality))
    return {"platform": "youtube", "quality": quality, "videos": results}
