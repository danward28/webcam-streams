"""Music playlist management — genre switching, concat file generation."""

import random
from pathlib import Path

import library

PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output"

GENRES = [
    "instrumental",
    "lo-fi",
    "jazz",
    "classical",
    "ambient",
    "acoustic",
    "electronic",
    "pop-covers",
]


class MusicManager:
    """Manages the music playlist for streaming."""

    def __init__(self):
        self.current_genre = "instrumental"
        self.playlist = []
        self._concat_file = None

    def set_genre(self, genre):
        """Switch to a different genre and rebuild playlist."""
        if genre in GENRES:
            self.current_genre = genre
        return self.build_playlist()

    def build_playlist(self, genre=None, shuffle=True):
        """Build a concat file from the music library for FFmpeg.

        Returns the path to the concat file, or None if no tracks available.
        """
        genre = genre or self.current_genre
        paths = library.get_playlist(asset_type="music", genre=genre, shuffle=shuffle)

        # If no tracks in the selected genre, fall back to all music
        if not paths:
            paths = library.get_playlist(asset_type="music", shuffle=shuffle)

        if not paths:
            return None

        self.playlist = paths
        OUTPUT_DIR.mkdir(exist_ok=True)
        concat_file = OUTPUT_DIR / "music_playlist.txt"

        with open(concat_file, "w") as f:
            for path in paths:
                f.write(f"file '{path}'\n")

        self._concat_file = str(concat_file)
        return self._concat_file

    def get_concat_file(self):
        """Return current concat file path, building if needed."""
        if self._concat_file and Path(self._concat_file).exists():
            return self._concat_file
        return self.build_playlist()

    def get_status(self):
        """Return current music state."""
        return {
            "genre": self.current_genre,
            "track_count": len(self.playlist),
            "genres": GENRES,
        }
