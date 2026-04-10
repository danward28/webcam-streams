"""Asset library — persistent storage for music tracks and video clips."""

import json
import os
import random
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PROJECT_DIR = Path(__file__).parent
LIBRARY_DIR = PROJECT_DIR / "library"
VIDEOS_DIR = LIBRARY_DIR / "videos"
MUSIC_DIR = LIBRARY_DIR / "music"
THUMBS_DIR = LIBRARY_DIR / "thumbnails"
CATALOG_FILE = LIBRARY_DIR / "catalog.json"

_lock = threading.Lock()


def _ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)


def _load_catalog():
    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_catalog(entries):
    _ensure_dirs()
    CATALOG_FILE.write_text(json.dumps(entries, indent=2) + "\n")


def _generate_thumbnail(video_path, thumb_path):
    """Extract first frame as thumbnail."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vframes", "1", "-s", "320x180",
             "-q:v", "5", str(thumb_path)],
            capture_output=True, timeout=30
        )
    except Exception:
        pass


def _get_duration(file_path):
    """Get duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(file_path)],
            capture_output=True, text=True, timeout=15
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def add(file_path, title="", artist="", genre="", generator="upload",
        asset_type="music"):
    """Add an asset to the library. Moves the file and catalogs it."""
    _ensure_dirs()
    asset_id = uuid4().hex[:8]
    ext = Path(file_path).suffix or (".mp3" if asset_type == "music" else ".mp4")

    if asset_type == "music":
        dest = MUSIC_DIR / f"{asset_id}{ext}"
    else:
        dest = VIDEOS_DIR / f"{asset_id}{ext}"

    shutil.move(str(file_path), str(dest))

    # Thumbnail for video assets
    if asset_type == "video":
        thumb = THUMBS_DIR / f"{asset_id}.jpg"
        _generate_thumbnail(dest, thumb)

    file_size = dest.stat().st_size / (1024 * 1024)
    duration = _get_duration(dest)

    entry = {
        "id": asset_id,
        "title": title,
        "artist": artist,
        "genre": genre,
        "generator": generator,
        "asset_type": asset_type,
        "duration_sec": round(duration, 1),
        "file_size_mb": round(file_size, 1),
        "created": datetime.now().isoformat(timespec="seconds"),
        "enabled": True,
        # Legacy compat fields
        "song": title,
        "movie": "",
        "style": genre,
    }

    with _lock:
        catalog = _load_catalog()
        catalog.append(entry)
        _save_catalog(catalog)

    return entry


def remove(asset_id):
    """Delete an asset from the library."""
    with _lock:
        catalog = _load_catalog()
        entry = next((e for e in catalog if e["id"] == asset_id), None)
        if not entry:
            return False
        catalog = [e for e in catalog if e["id"] != asset_id]
        _save_catalog(catalog)

    # Try to remove file from both directories
    for directory in [MUSIC_DIR, VIDEOS_DIR]:
        for f in directory.iterdir():
            if f.stem == asset_id:
                f.unlink()
                break
    thumb = THUMBS_DIR / f"{asset_id}.jpg"
    if thumb.exists():
        thumb.unlink()
    return True


def toggle(asset_id):
    """Toggle enabled/disabled for an asset."""
    with _lock:
        catalog = _load_catalog()
        for entry in catalog:
            if entry["id"] == asset_id:
                entry["enabled"] = not entry["enabled"]
                _save_catalog(catalog)
                return entry["enabled"]
    return None


def list_assets(asset_type=None, genre=None, generator=None, enabled_only=False):
    """List library assets with optional filtering."""
    catalog = _load_catalog()
    if asset_type:
        catalog = [e for e in catalog if e.get("asset_type") == asset_type]
    if genre:
        catalog = [e for e in catalog if e.get("genre") == genre]
    if generator:
        catalog = [e for e in catalog if e.get("generator") == generator]
    if enabled_only:
        catalog = [e for e in catalog if e.get("enabled", True)]
    return catalog


def get_asset(asset_id):
    """Get a single asset entry."""
    catalog = _load_catalog()
    return next((e for e in catalog if e["id"] == asset_id), None)


def get_music_path(asset_id):
    """Get the filesystem path for a music asset."""
    for f in MUSIC_DIR.iterdir():
        if f.stem == asset_id:
            return str(f)
    return None


def get_video_path(asset_id):
    """Get the filesystem path for a video asset."""
    for f in VIDEOS_DIR.iterdir():
        if f.stem == asset_id:
            return str(f)
    return None


def get_thumb_path(asset_id):
    """Get the filesystem path for an asset's thumbnail."""
    path = THUMBS_DIR / f"{asset_id}.jpg"
    return str(path) if path.exists() else None


def get_playlist(asset_type="music", genre=None, shuffle=True):
    """Get list of enabled file paths for streaming/playback."""
    assets = list_assets(asset_type=asset_type, genre=genre, enabled_only=True)
    if shuffle:
        random.shuffle(assets)

    directory = MUSIC_DIR if asset_type == "music" else VIDEOS_DIR
    paths = []
    for a in assets:
        for f in directory.iterdir():
            if f.stem == a["id"]:
                paths.append(str(f))
                break
    return paths


def stats():
    """Library statistics."""
    catalog = _load_catalog()
    music = [e for e in catalog if e.get("asset_type") == "music"]
    enabled_music = [e for e in music if e.get("enabled", True)]
    total_duration = sum(e.get("duration_sec", 0) for e in enabled_music)
    total_size = sum(e.get("file_size_mb", 0) for e in catalog)

    by_genre = {}
    for e in music:
        g = e.get("genre", "untagged")
        by_genre[g] = by_genre.get(g, 0) + 1

    by_generator = {}
    for e in catalog:
        g = e.get("generator", "unknown")
        by_generator[g] = by_generator.get(g, 0) + 1

    return {
        "total": len(catalog),
        "music_total": len(music),
        "music_enabled": len(enabled_music),
        "enabled": len(enabled_music),
        "total_duration_sec": round(total_duration, 1),
        "total_duration_min": round(total_duration / 60, 1),
        "total_size_mb": round(total_size, 1),
        "by_genre": by_genre,
        "by_generator": by_generator,
    }
