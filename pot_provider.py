"""
pot_provider.py
----------------
موديول يدير تشغيل/إيقاف خادم PO Token (bgutil-ytdlp-pot-provider)
كـ subprocess داخلي على منفذ محلي، عشان yt-dlp يقدر يستخدمه
لتحميل فيديوهات يوتيوب العامة بدون كوكيز حساب بشري.

ضع هذا الملف داخل مجلد المشروع (مثلاً بجانب utils/) واستورده من main.py
"""

import subprocess
import time
import socket
import logging
import atexit

logger = logging.getLogger("pot_provider")

POT_SERVER_PORT = 4416
POT_SERVER_HOST = "127.0.0.1"
POT_SERVER_BASE_URL = f"http://{POT_SERVER_HOST}:{POT_SERVER_PORT}"

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

    try:
        # الأمر الفعلي يعتمد على طريقة تشغيل النسخة اللي ثبتها من الحزمة.
        # عدّل هذا السطر حسب الأمر الموثق فعليًا بحزمة bgutil-ytdlp-pot-provider
        # (تحقق من التوثيق وقت التنفيذ، لأنه قد يختلف بين الإصدارات).
        _pot_process = subprocess.Popen(
            [
                "python",
                "-m",
                "bgutil_ytdlp_pot_provider.server",
                "--port",
                str(POT_SERVER_PORT),
                "--host",
                POT_SERVER_HOST,
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
