"""Webcam directory — searchable database of known public webcam streams.

Combines a curated static database with live YouTube search for discovering
new webcam sources. Sources can be browsed by category and added to the
active source list with one click.
"""

import json
import re
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
DIRECTORY_FILE = PROJECT_DIR / "webcams" / "directory.json"

# ── Categories ───────────────────────────────────────────────────────────────

CATEGORIES = [
    "disney", "newengland", "beach", "city", "national-parks",
    "northern-lights", "mountain", "wildlife", "european", "tropical",
    "other",
]

CATEGORY_LABELS = {
    "disney": "Disney Parks",
    "newengland": "New England",
    "beach": "Beach & Coastal",
    "city": "City Skylines",
    "national-parks": "National Parks",
    "northern-lights": "Northern Lights",
    "mountain": "Mountain & Alpine",
    "wildlife": "Wildlife",
    "european": "European Charm",
    "tropical": "Tropical Islands",
    "other": "Other",
}


# ── Static Directory (curated known streams) ─────────────────────────────────

# This is the built-in database of known public webcam channels and streams.
# Each entry is a known source that can be added to the active sources list.
# The 'search_hints' help with YouTube discovery queries.

KNOWN_CHANNELS = [
    # ── Major Webcam Networks ──
    {
        "channel": "EarthCam",
        "youtube_channel": "EarthCam",
        "categories": ["city", "beach", "other"],
        "search_hints": ["earthcam live", "earthcam times square", "earthcam abbey road"],
        "notes": "Major webcam network — Times Square, Abbey Road, beaches, cities worldwide",
    },
    {
        "channel": "explore.org",
        "youtube_channel": "explore",
        "categories": ["wildlife", "national-parks"],
        "search_hints": ["explore.org live", "explore bear cam", "explore eagle cam"],
        "notes": "Wildlife cams — Katmai bears, bald eagles, African wildlife, ocean cams",
    },
    {
        "channel": "SkylineWebcams",
        "youtube_channel": "SkylineWebcams",
        "categories": ["european", "beach", "city"],
        "search_hints": ["skylinewebcams live", "skylinewebcams venice", "skylinewebcams rome"],
        "notes": "European cities, beaches, volcanoes — Venice, Rome, Etna, Santorini",
    },
    # ── Surf & Beach ──
    {
        "channel": "Surfline",
        "youtube_channel": "Surfline",
        "categories": ["beach"],
        "search_hints": ["surfline live cam", "surfline pipeline", "surfline huntington"],
        "notes": "Surf cams worldwide — Pipeline, Huntington, Mavericks, Gold Coast",
    },
    {
        "channel": "The Surfing Lifestyle",
        "youtube_channel": "The Surfing Lifestyle",
        "categories": ["beach", "tropical"],
        "search_hints": ["surfing lifestyle live cam"],
        "notes": "Beach and surf cams",
    },
    # ── National Parks & Nature ──
    {
        "channel": "National Park Service",
        "youtube_channel": "NationalParkService",
        "categories": ["national-parks"],
        "search_hints": ["national park service live", "old faithful live", "yellowstone live cam"],
        "notes": "Official NPS cams — Old Faithful, Grand Canyon, Yellowstone",
    },
    {
        "channel": "Wyoming Webcams",
        "youtube_channel": "",
        "categories": ["national-parks", "mountain"],
        "search_hints": ["yellowstone live cam 24/7", "grand teton live cam", "wyoming webcam"],
        "notes": "Wyoming scenic and park webcams",
    },
    # ── Wildlife ──
    {
        "channel": "Cornell Lab Bird Cams",
        "youtube_channel": "CornellLabBirdCams",
        "categories": ["wildlife"],
        "search_hints": ["cornell bird cam live", "cornell hawk cam", "cornell feeder cam"],
        "notes": "Bird nest cams, feeder cams — red-tailed hawks, owls, feeders",
    },
    {
        "channel": "Monterey Bay Aquarium",
        "youtube_channel": "MontereyBayAquarium",
        "categories": ["wildlife"],
        "search_hints": ["monterey bay aquarium live cam", "sea otter cam", "kelp forest cam"],
        "notes": "Ocean cams — sea otters, jellyfish, kelp forest, shark cam",
    },
    # ── Northern Lights ──
    {
        "channel": "Churchill Northern Studies",
        "youtube_channel": "",
        "categories": ["northern-lights"],
        "search_hints": ["churchill northern lights live", "aurora borealis live cam churchill"],
        "notes": "Aurora cam from Churchill, Manitoba",
    },
    {
        "channel": "Lights Over Lapland",
        "youtube_channel": "",
        "categories": ["northern-lights"],
        "search_hints": ["aurora live cam sweden", "northern lights live sweden", "lights over lapland"],
        "notes": "Aurora cam from Abisko, Sweden",
    },
    # ── Cities ──
    {
        "channel": "I Love You Amsterdam",
        "youtube_channel": "",
        "categories": ["european", "city"],
        "search_hints": ["amsterdam live cam", "amsterdam canal live"],
        "notes": "Amsterdam canal and city views",
    },
    {
        "channel": "Venice Italy Live Cam",
        "youtube_channel": "",
        "categories": ["european"],
        "search_hints": ["venice live cam", "venice st marks square live", "rialto bridge live cam"],
        "notes": "Venice — St. Mark's Square, Rialto Bridge, Grand Canal",
    },
    {
        "channel": "Tokyo Live Camera",
        "youtube_channel": "",
        "categories": ["city"],
        "search_hints": ["tokyo live cam", "shibuya crossing live", "tokyo tower live cam"],
        "notes": "Tokyo — Shibuya Crossing, Tokyo Tower, Shinjuku",
    },
    # ── Mountains ──
    {
        "channel": "Zermatt Tourism",
        "youtube_channel": "",
        "categories": ["mountain", "european"],
        "search_hints": ["matterhorn live cam", "zermatt live cam", "swiss alps live"],
        "notes": "Matterhorn / Zermatt views",
    },
    # ── Tropical ──
    {
        "channel": "Hawaii Tourism",
        "youtube_channel": "",
        "categories": ["tropical", "beach"],
        "search_hints": ["waikiki beach live cam", "hawaii live cam 24/7", "maui beach live"],
        "notes": "Hawaiian beach cams",
    },
    {
        "channel": "Key West",
        "youtube_channel": "",
        "categories": ["tropical", "beach"],
        "search_hints": ["key west live cam", "mallory square live cam", "duval street live cam"],
        "notes": "Key West — Mallory Square, Duval Street, harbor",
    },
    # ── Disney ──
    {
        "channel": "Disney Area Cams",
        "youtube_channel": "",
        "categories": ["disney"],
        "search_hints": ["disney springs live cam", "disney resort area live", "orlando theme park live cam", "disney fireworks live cam"],
        "notes": "Disney resort area webcams (public cams near Disney, not official Disney cams)",
    },
]


# ── Custom directory entries (user-discovered, saved to disk) ────────────────

def _load_directory():
    """Load the user's discovered/saved directory entries."""
    if DIRECTORY_FILE.exists():
        try:
            return json.loads(DIRECTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_directory(entries):
    DIRECTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIRECTORY_FILE.write_text(json.dumps(entries, indent=2) + "\n")


def save_to_directory(name, url, source_type, category, notes=""):
    """Save a discovered stream to the local directory for future reference."""
    entries = _load_directory()
    entry = {
        "name": name,
        "url": url,
        "type": source_type,
        "category": category,
        "notes": notes,
    }
    # Avoid duplicates by URL
    if not any(e["url"] == url for e in entries):
        entries.append(entry)
        _save_directory(entries)
    return entry


def remove_from_directory(url):
    """Remove a saved directory entry by URL."""
    entries = _load_directory()
    entries = [e for e in entries if e["url"] != url]
    _save_directory(entries)


def list_directory(category=None):
    """List all saved directory entries, optionally filtered by category."""
    entries = _load_directory()
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return entries


# ── YouTube Search ───────────────────────────────────────────────────────────

def search_youtube(query, max_results=20):
    """Search YouTube for live webcam streams using yt-dlp.

    Returns a list of dicts with: url, title, channel, duration, is_live, thumbnail.
    """
    try:
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-download",
            "--playlist-end", str(max_results),
            f"ytsearch{max_results}:{query} live cam",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []

        streams = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                streams.append({
                    "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                    "title": data.get("title", "Unknown"),
                    "channel": data.get("channel", data.get("uploader", "Unknown")),
                    "duration": data.get("duration"),
                    "is_live": data.get("is_live", False),
                    "thumbnail": data.get("thumbnail", ""),
                    "view_count": data.get("view_count", 0),
                })
            except json.JSONDecodeError:
                continue

        # Sort live streams first, then by view count
        streams.sort(key=lambda s: (not s.get("is_live", False),
                                    -(s.get("view_count") or 0)))
        return streams

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def search_by_category(category):
    """Search YouTube using the known channel hints for a category."""
    hints = []
    for ch in KNOWN_CHANNELS:
        if category in ch.get("categories", []):
            hints.extend(ch.get("search_hints", []))

    # Also add generic searches
    label = CATEGORY_LABELS.get(category, category)
    hints.append(f"{label} live webcam 24/7")

    # Deduplicate and pick the best 3 search queries
    seen = set()
    unique_hints = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            unique_hints.append(h)

    # Search with top hints and merge results
    all_results = []
    seen_urls = set()
    for hint in unique_hints[:3]:
        results = search_youtube(hint, max_results=10)
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_results.append(r)

    # Sort: live first, then by view count
    all_results.sort(key=lambda s: (not s.get("is_live", False),
                                     -(s.get("view_count") or 0)))
    return all_results[:30]


def get_suggested_searches(category=None):
    """Get a list of suggested search queries for a category (or all)."""
    hints = []
    for ch in KNOWN_CHANNELS:
        if category is None or category in ch.get("categories", []):
            for h in ch.get("search_hints", []):
                if h not in hints:
                    hints.append(h)
    return hints


def get_known_channels(category=None):
    """Get known webcam channels/networks, optionally filtered by category."""
    if category is None:
        return KNOWN_CHANNELS
    return [ch for ch in KNOWN_CHANNELS if category in ch.get("categories", [])]
