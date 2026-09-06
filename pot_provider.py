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

    # === تعديل جديد: نضيف جذر المشروع لـ PATH ===
    # الـ Plugin (getpot_bgutil_cli.py) يحاول يشغّل "bgutil-pot" كأمر مباشر
    # معتمدًا إنه موجود بـ PATH النظام. بإضافة جذر المشروع هنا، أي subprocess
    # يشتغل بعد هذا السطر (بما فيها استدعاءات الـ Plugin الداخلية أثناء
    # معالجة الطلبات) بيقدر يلقى الملف تلقائيًا بغض النظر عن المجلد اللي
    # يُستدعى منه، لأن العمليات الفرعية ترث متغيرات البيئة من هذي العملية.
    if _PROJECT_ROOT not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _PROJECT_ROOT + os.pathsep + os.environ.get("PATH", "")

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


def get_pot_status() -> dict:
    """
    يفحص الحالة الحقيقية لخادم POT والعميل، ويرجع تقرير JSON كامل.
    يُستخدم فقط للتشخيص المؤقت عبر /debug/pot-status، لا يُغيّر أي سلوك تشغيلي.
    """
    status: dict = {}

    status["binary_exists"] = os.path.isfile(POT_BINARY_PATH)
    status["binary_executable"] = (
        os.access(POT_BINARY_PATH, os.X_OK) if status["binary_exists"] else False
    )

    status["port_open"] = _is_port_open(POT_SERVER_HOST, POT_SERVER_PORT)

    if _pot_process is not None:
        status["process_tracked"] = True
        status["process_alive"] = _pot_process.poll() is None
    else:
        status["process_tracked"] = False
        status["process_alive"] = None

    try:
        import urllib.request

        with urllib.request.urlopen(POT_SERVER_BASE_URL, timeout=2) as resp:
            status["http_reachable"] = True
            status["http_status_code"] = resp.status
    except Exception as e:
        status["http_reachable"] = False
        status["http_error"] = f"{type(e).__name__}: {e}"

    try:
        import importlib.metadata as _md

        status["client_package_version"] = _md.version(
            "bgutil-ytdlp-pot-provider"
        )
    except Exception as e:
        status["client_package_version"] = None
        status["client_package_error"] = f"{type(e).__name__}: {e}"

    try:
        import yt_dlp.extractor as _ext

        plugin_names = [
            name
            for name in dir(_ext)
            if "bgutil" in name.lower() or "pot" in name.lower()
        ]
        status["ytdlp_pot_related_extractors"] = plugin_names
    except Exception as e:
        status["ytdlp_pot_related_extractors"] = None
        status["ytdlp_check_error"] = f"{type(e).__name__}: {e}"

    return status


atexit.register(stop_pot_server)
