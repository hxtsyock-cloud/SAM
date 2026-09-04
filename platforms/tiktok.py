import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from typing import List, Dict

IMPERSONATE_TARGET = ImpersonateTarget.from_str("chrome")

def matches_url(video_url: str) -> bool:
    return "tiktok.com" in video_url

def download_by_url(video_url: str) -> Dict:
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "%(id)s.%(ext)s",
        "impersonate": IMPERSONATE_TARGET,
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "Referer": "https://www.tiktok.com/",
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "tiktok",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "ext": info.get("ext"),
            "filepath": ydl.prepare_filename(info),
        }

def download_by_username(username: str) -> Dict:
    url = f"https://www.tiktok.com/@{username}"
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "%(id)s.%(ext)s",
        "impersonate": IMPERSONATE_TARGET,
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "Referer": "https://www.tiktok.com/",
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        videos = info.get("entries", [])
        return {
            "platform": "tiktok",
            "username": username,
            "videos": [
                {"video_id": v.get("id"), "title": v.get("title")}
                for v in videos
            ],
        }

def download_by_ids(video_ids: List[str]) -> Dict:
    results = []
    for vid in video_ids:
        url = f"https://www.tiktok.com/@_/video/{vid}"
        results.append(download_by_url(url))
    return {"platform": "tiktok", "videos": results}