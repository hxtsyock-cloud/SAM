"""
pot_provider.py
----------------
موديول يدير تشغيل/إيقاف خادم PO Token (bgutil-ytdlp-pot-provider)
كـ subprocess داخلي على منفذ محلي، عشان yt-dlp يقدر يستخدمه
لتحميل فيديوهات يوتيوب العامة بدون كوكيز حساب بشري.

ضع هذا الملف داخل مجلد المشروع (مثلاً بجانب utils/) واستورده من main.py
"""

import os
import subprocess
import time
import socket
import logging
import atexit

logger = logging.getLogger("pot_provider")

POT_SERVER_PORT = 4416
POT_SERVER_HOST = "127.0.0.1"
POT_SERVER_BASE_URL = f"http://{POT_SERVER_HOST}:{POT_SERVER_PORT}"

# مسار الملف التنفيذي (binary) اللي يُنزَّل وقت البناء على Render
# عبر Build Command — راجع render_build_command.txt
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
POT_BINARY_PATH = os.path.join(_PROJECT_ROOT, "bgutil-pot")

_pot_process: subprocess.Popen | None = None


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """يتأكد إن المنفذ صاير يستقبل اتصالات (يعني الخادم شغّال فعليًا)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_pot_server(max_wait_seconds: int = 15) -> bool:
    """
    يشغّل خادم POT كـ subprocess ويتأكد إنه صار جاهز قبل الرجوع.
    يُستدعى مرة وحدة عند إقلاع FastAPI (startup_event).

    يرجع True لو نجح التشغيل والتأكد من الجاهزية، False غير ذلك.
    """
    global _pot_process

    if _is_port_open(POT_SERVER_HOST, POT_SERVER_PORT):
        logger.info("POT server already running on port %s", POT_SERVER_PORT)
        return True

    if not os.path.isfile(POT_BINARY_PATH):
        logger.error(
            "POT server binary not found at %s — did the Render build step "
            "download it? See render_build_command.txt",
            POT_BINARY_PATH,
        )
        return False

    if not os.access(POT_BINARY_PATH, os.X_OK):
        try:
            os.chmod(POT_BINARY_PATH, 0o755)
        except OSError:
            logger.exception("Failed to make POT binary executable")
            return False

    try:
        _pot_process = subprocess.Popen(
            [
                POT_BINARY_PATH,
                "server",
                "--host",
                POT_SERVER_HOST,
                "--port",
                str(POT_SERVER_PORT),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception:
        logger.exception("Failed to start POT server process")
        return False

    # ننتظر لين المنفذ يصير جاهز، بدل ما نفترض إنه جاهز فورًا
    waited = 0.0
    interval = 0.5
    while waited < max_wait_seconds:
        if _is_port_open(POT_SERVER_HOST, POT_SERVER_PORT):
            logger.info("POT server is ready on %s", POT_SERVER_BASE_URL)
            return True
        time.sleep(interval)
        waited += interval

    logger.error("POT server did not become ready within %ss", max_wait_seconds)
    return False


def stop_pot_server() -> None:
    """يوقف خادم POT بأمان عند إغلاق التطبيق."""
    global _pot_process
    if _pot_process is not None and _pot_process.poll() is None:
        logger.info("Stopping POT server subprocess")
        _pot_process.terminate()
        try:
            _pot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _pot_process.kill()
    _pot_process = None


# يضمن إيقاف الخادم حتى لو التطبيق انتهى بشكل غير متوقع
atexit.register(stop_pot_server)
