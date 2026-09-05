import os
import shutil
from typing import Dict

import yt_dlp

from utils.quality import format_selector


def matches_url(video_url: str) -> bool:
    return "facebook.com" in video_url or "fb.watch" in video_url


def download_by_url(video_url: str, quality: str = "best") -> Dict:
    # نسخ ملف الكوكيز من المجلد المحمي (read-only) إلى مجلد مؤقت قابل للكتابة
    source_cookies = "/etc/secrets/facebook_cookies.txt"
    writable_cookies = "/tmp/facebook_cookies.txt"

    ydl_opts = {
        "format": format_selector(quality, "facebook"),
        "outtmpl": "%(id)s.%(ext)s",
    }

    if os.path.exists(source_cookies):
        shutil.copy(source_cookies, writable_cookies)
        ydl_opts["cookiefile"] = writable_cookies

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return {
            "platform": "facebook",
            "video_id": info.get("id"),
            "title": info.get("title"),
            "quality": quality,
            "filepath": ydl.prepare_filename(info),
        }
