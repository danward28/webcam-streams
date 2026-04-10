"""Webcam source catalog — CRUD, health checks, and URL resolution."""

import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PROJECT_DIR = Path(__file__).parent
WEBCAMS_DIR = PROJECT_DIR / "webcams"
SOURCES_FILE = WEBCAMS_DIR / "sources.json"

_lock = threading.Lock()


def _ensure_dirs():
    WEBCAMS_DIR.mkdir(parents=True, exist_ok=True)


def _load_sources():
    if SOURCES_FILE.exists():
        try:
            return json.loads(SOURCES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_sources(sources):
    _ensure_dirs()
    SOURCES_FILE.write_text(json.dumps(sources, indent=2) + "\n")


# ── CRUD ────────────────────────────────────────────────────────────────────


def add_source(name, url, source_type="youtube_live", category="", notes=""):
    """Add a new webcam source."""
    source = {
        "id": uuid4().hex[:8],
        "name": name,
        "url": url.strip(),
        "type": source_type,  # youtube_live | hls | rtsp | mjpeg
        "category": category,
        "enabled": True,
        "status": "unknown",  # online | offline | degraded | unknown
        "last_check": None,
        "fail_count": 0,
        "added": datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
    }
    with _lock:
        sources = _load_sources()
        sources.append(source)
        _save_sources(sources)
    return source


def remove_source(source_id):
    """Delete a source by ID."""
    with _lock:
        sources = _load_sources()
        sources = [s for s in sources if s["id"] != source_id]
        _save_sources(sources)
    return True


def toggle_source(source_id):
    """Toggle enabled/disabled for a source."""
    with _lock:
        sources = _load_sources()
        for s in sources:
            if s["id"] == source_id:
                s["enabled"] = not s["enabled"]
                _save_sources(sources)
                return s["enabled"]
    return None


def update_status(source_id, status, fail_count=None):
    """Update source status after a health check."""
    with _lock:
        sources = _load_sources()
        for s in sources:
            if s["id"] == source_id:
                s["status"] = status
                s["last_check"] = datetime.now().isoformat(timespec="seconds")
                if fail_count is not None:
                    s["fail_count"] = fail_count
                _save_sources(sources)
                return True
    return False


def list_sources(category=None, enabled_only=False):
    """List sources with optional filters."""
    sources = _load_sources()
    if category:
        sources = [s for s in sources if s.get("category") == category]
    if enabled_only:
        sources = [s for s in sources if s.get("enabled", True)]
    return sources


def get_source(source_id):
    """Get a single source by ID."""
    sources = _load_sources()
    return next((s for s in sources if s["id"] == source_id), None)


def get_active_playlist(category=None):
    """Get list of enabled + online/unknown sources for streaming."""
    sources = list_sources(category=category, enabled_only=True)
    return [s for s in sources if s.get("status") in ("online", "unknown")]


def stats():
    """Source statistics."""
    sources = _load_sources()
    enabled = [s for s in sources if s.get("enabled", True)]
    online = [s for s in enabled if s.get("status") == "online"]
    by_category = {}
    for s in sources:
        cat = s.get("category", "uncategorized")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(sources),
        "enabled": len(enabled),
        "online": len(online),
        "by_category": by_category,
    }


# ── URL Resolution ──────────────────────────────────────────────────────────


def resolve_stream_url(source):
    """Resolve the actual stream URL for FFmpeg.

    For YouTube live streams, uses yt-dlp to extract the HLS manifest URL.
    For direct HLS/RTSP/MJPEG, returns the URL as-is.
    """
    url = source["url"]
    source_type = source.get("type", "youtube_live")

    if source_type == "youtube_live":
        try:
            result = subprocess.run(
                ["yt-dlp", "-f", "best[height<=1080]", "--get-url", url],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # HLS, RTSP, MJPEG — return URL directly
    return url


# ── Health Checks ───────────────────────────────────────────────────────────


def test_source(url, source_type="youtube_live"):
    """Test whether a webcam source is reachable. Returns (ok, info)."""
    if source_type == "youtube_live":
        try:
            result = subprocess.run(
                ["yt-dlp", "--simulate", "--no-download", url],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "Stream is live"
            return False, result.stderr.strip()[-200:] if result.stderr else "Not available"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except FileNotFoundError:
            return False, "yt-dlp not installed"

    elif source_type in ("hls", "rtsp"):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-timeout", "5000000",
                 "-print_format", "json", "-show_format", url],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return True, "Stream reachable"
            return False, "Cannot connect"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Timeout or ffprobe not found"

    elif source_type == "mjpeg":
        import urllib.request
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10):
                return True, "MJPEG endpoint reachable"
        except Exception as e:
            return False, str(e)[:200]

    return False, f"Unknown source type: {source_type}"


MAX_FAIL_COUNT = 3


def health_check_all():
    """Run health checks on all enabled sources. Auto-disable after repeated failures."""
    sources = list_sources(enabled_only=True)
    results = []

    for source in sources:
        ok, info = test_source(source["url"], source["type"])
        fail_count = source.get("fail_count", 0)

        if ok:
            update_status(source["id"], "online", fail_count=0)
            results.append((source["id"], source["name"], "online", info))
        else:
            fail_count += 1
            if fail_count >= MAX_FAIL_COUNT:
                update_status(source["id"], "offline", fail_count=fail_count)
                # Auto-disable after MAX_FAIL_COUNT consecutive failures
                toggle_source(source["id"])
                results.append((source["id"], source["name"], "offline (auto-disabled)", info))
            else:
                update_status(source["id"], "degraded", fail_count=fail_count)
                results.append((source["id"], source["name"], f"degraded ({fail_count}/{MAX_FAIL_COUNT})", info))

    return results


class HealthChecker:
    """Background thread that periodically checks all webcam sources."""

    def __init__(self, interval_sec=300):
        self.interval = interval_sec
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        # Initial check after a short delay
        self._stop.wait(30)
        while not self._stop.is_set():
            try:
                health_check_all()
            except Exception:
                pass
            self._stop.wait(self.interval)
