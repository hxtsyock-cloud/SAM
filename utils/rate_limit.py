from fastapi import Request, HTTPException
from threading import Lock
from typing import Dict
import time

_requests: Dict[str, Dict] = {}
_lock = Lock()
WINDOW_SECONDS = 60
MAX_REQUESTS = 30

def rate_limit(request: Request, limit: int = MAX_REQUESTS):
    ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    with _lock:
        entry = _requests.get(ip, {"count": 0, "start": now})
        if now - entry["start"] >= WINDOW_SECONDS:
            entry = {"count": 0, "start": now}
        entry["count"] += 1
        _requests[ip] = entry
        if entry["count"] > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
