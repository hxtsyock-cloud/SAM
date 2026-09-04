import yt_dlp
import shutil
import os
from typing import Dict

def matches_url(video_url: str) -> bool:
    return "facebook.com" in video_url or "fb.watch" in video_url

def download_by_url(video_url: str) -> Dict:
    # نسخ ملف الكوكيز من المجلد المحمي (read-only) إلى مجلد مؤقت قابل للكتابة
    source_cookies = "/etc/secrets/facebook_cookies.txt"
    writable_cookies = "/tmp/facebook_cookies.txt"

    ydl_opts = {
        "format": "best",
        "outtmpl": "%(id)s.%(ext)s",
    }

    if os.path.exists(source_cookies):
        shutil.copy(source_cookies, writable_cookies)
        ydl_opts["cookiefile"] = writable_cookies
