from typing import Dict

import yt_dlp

from utils.quality import format_selector


def matches_url(video_url: str) -> bool:
    return "snapchat.com" in video_url


def download_by_url(video_url: str, quality: str = "best") -> Dict:
    ydl_opts = {
        "format": format_selector(quality, "snapchat"),
        "outtmpl": "%(id)s.%(ext)s",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "snapchat",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "quality": quality,
            "filepath": ydl.prepare_filename(info),
        }
