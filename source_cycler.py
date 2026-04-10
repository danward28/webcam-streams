"""Timer-based webcam source cycling."""

import threading

import webcam_sources


class SourceCycler:
    """Cycles through webcam sources on a configurable timer."""

    def __init__(self, stream_manager, cycle_interval_sec=600):
        self.stream_mgr = stream_manager
        self.cycle_interval = cycle_interval_sec
        self.sources = []
        self.current_index = 0
        self._thread = None
        self._stop = threading.Event()
        self._callbacks = []

    def start(self, sources=None):
        """Start cycling through sources."""
        if sources:
            self.sources = sources
        if not self.sources:
            self.sources = webcam_sources.get_active_playlist()
        if not self.sources:
            return False

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop the cycling timer."""
        self._stop.set()

    def reload_sources(self):
        """Refresh the source list from disk."""
        self.sources = webcam_sources.get_active_playlist()
        if self.current_index >= len(self.sources):
            self.current_index = 0

    def skip(self):
        """Skip to the next source immediately."""
        self._advance()

    def get_current_source(self):
        """Return the currently active source."""
        if self.sources and self.current_index < len(self.sources):
            return self.sources[self.current_index]
        return None

    def get_status(self):
        """Return cycler state."""
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "cycle_interval_sec": self.cycle_interval,
            "total_sources": len(self.sources),
            "current_index": self.current_index,
            "current_source": self.get_current_source(),
        }

    def set_interval(self, seconds):
        """Update the cycle interval."""
        self.cycle_interval = max(60, seconds)  # minimum 1 minute

    def register_callback(self, cb):
        """Register callback(source) called on each source change."""
        self._callbacks.append(cb)

    def _notify(self, source):
        for cb in list(self._callbacks):
            try:
                cb(source)
            except Exception:
                pass

    def _run(self):
        """Timer loop: wait for interval then advance to next source."""
        while not self._stop.is_set():
            self._stop.wait(self.cycle_interval)
            if self._stop.is_set():
                break
            self._advance()

    def _advance(self):
        """Move to next source and tell the stream manager to switch."""
        if not self.sources:
            self.reload_sources()
            if not self.sources:
                return

        self.current_index = (self.current_index + 1) % len(self.sources)
        source = self.sources[self.current_index]

        result = self.stream_mgr.switch_source(source)
        if not result.get("ok"):
            # Source failed — try next one
            for _ in range(len(self.sources) - 1):
                self.current_index = (self.current_index + 1) % len(self.sources)
                source = self.sources[self.current_index]
                result = self.stream_mgr.switch_source(source)
                if result.get("ok"):
                    break
            else:
                return  # All sources failed

        self._notify(source)
