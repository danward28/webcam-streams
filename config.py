"""Centralized configuration for Webcam Streams — theme-aware."""

import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CONFIG_JSON = PROJECT_DIR / "config.json"
ENV_FILE = PROJECT_DIR / ".env"
THEME_DIR = PROJECT_DIR / "themes"

# Active theme (set via STREAM_THEME env var or default to "beach")
THEME = os.environ.get("STREAM_THEME", "beach")


def _load_env():
    """Read .env file into os.environ (simple key=value parser)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def _load_json_config():
    """Load mutable runtime config from config.json."""
    if CONFIG_JSON.exists():
        try:
            return json.loads(CONFIG_JSON.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json_config(data):
    CONFIG_JSON.write_text(json.dumps(data, indent=2) + "\n")


def _load_theme():
    """Load theme config from themes/<name>.json."""
    theme_file = THEME_DIR / f"{THEME}.json"
    if theme_file.exists():
        try:
            return json.loads(theme_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


# Load on import
_load_env()
_json_config = _load_json_config()
_theme_config = _load_theme()


def get(key, default=None):
    """Get config value. Priority: config.json > env var > theme > default."""
    if key in _json_config:
        return _json_config[key]
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return default


def set_runtime(key, value):
    """Set a runtime config value (persisted to config.json)."""
    _json_config[key] = value
    _save_json_config(_json_config)


def get_theme():
    """Return the full theme config dict."""
    return _theme_config


def get_theme_name():
    """Return the active theme slug."""
    return THEME


def get_all():
    """Return all config as a dict for the settings page."""
    return {
        "YOUTUBE_STREAM_KEY": get("YOUTUBE_STREAM_KEY", ""),
        "ANTHROPIC_API_KEY": get("ANTHROPIC_API_KEY", ""),
        "SUNO_API_KEY": get("SUNO_API_KEY", ""),
        "FLASK_PORT": int(get("FLASK_PORT", 8080)),
        "STREAM_THEME": THEME,
        "CYCLE_INTERVAL": int(get("CYCLE_INTERVAL",
                                  _theme_config.get("cycle_interval_sec", 600))),
        "DEFAULT_GENRE": get("DEFAULT_GENRE",
                             _theme_config.get("default_genre", "instrumental")),
    }
