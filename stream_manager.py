"""FFmpeg RTMP stream manager — webcam source + music + overlay composition."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import overlays
import webcam_sources

PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output"


class StreamManager:
    """Manages the FFmpeg streaming process with webcam + music + overlay."""

    def __init__(self):
        self.process = None
        self.status = "stopped"  # stopped | starting | live | error
        self.stream_key = None
        self.current_source = None
        self._start_time = None
        self._source_start_time = None
        self._monitor_thread = None
        self._error_msg = ""
        self._music_concat_file = None

    def start(self, stream_key, source, music_concat_file):
        """Start streaming a webcam source with music to YouTube."""
        if self.process and self.process.poll() is None:
            return {"ok": False, "error": "Stream already running"}

        stream_url = webcam_sources.resolve_stream_url(source)
        if not stream_url:
            return {"ok": False, "error": f"Cannot resolve URL for {source['name']}"}

        if not music_concat_file or not Path(music_concat_file).exists():
            return {"ok": False, "error": "No music playlist available"}

        # Initialize overlay system
        overlays.init()
        overlay_path = str(overlays.CURRENT_OVERLAY)

        cmd = self._build_ffmpeg_cmd(stream_url, music_concat_file,
                                     overlay_path, stream_key)

        self.status = "starting"
        self.stream_key = stream_key
        self._music_concat_file = music_concat_file
        self._error_msg = ""

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._start_time = time.time()
            self._source_start_time = time.time()
            self.current_source = source
            self.status = "live"

            self._monitor_thread = threading.Thread(
                target=self._monitor, daemon=True
            )
            self._monitor_thread.start()

            return {"ok": True, "pid": self.process.pid}
        except Exception as e:
            self.status = "error"
            self._error_msg = str(e)
            return {"ok": False, "error": str(e)}

    def stop(self):
        """Stop the stream gracefully."""
        if not self.process or self.process.poll() is not None:
            self.status = "stopped"
            return {"ok": True}

        try:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        self.status = "stopped"
        self.process = None
        self.current_source = None
        self._start_time = None
        self._source_start_time = None
        return {"ok": True}

    def switch_source(self, source):
        """Switch to a new webcam source with minimal stream interruption.

        Starts a new FFmpeg process, waits for it to stabilize, then kills
        the old one. YouTube absorbs the brief (~2-3s) glitch.
        """
        if not self.stream_key:
            return {"ok": False, "error": "No stream key configured"}

        stream_url = webcam_sources.resolve_stream_url(source)
        if not stream_url:
            return {"ok": False, "error": f"Cannot resolve URL for {source['name']}"}

        overlay_path = str(overlays.CURRENT_OVERLAY)
        cmd = self._build_ffmpeg_cmd(stream_url, self._music_concat_file,
                                     overlay_path, self.stream_key)

        old_process = self.process
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Wait for new process to establish RTMP connection
            time.sleep(2)

            if self.process.poll() is not None:
                # New process died immediately — revert
                self.process = old_process
                return {"ok": False, "error": "New source failed to start"}

            # Kill old process
            if old_process and old_process.poll() is None:
                old_process.send_signal(signal.SIGTERM)
                try:
                    old_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    old_process.kill()

            self.current_source = source
            self._source_start_time = time.time()

            # Restart monitor on new process
            self._monitor_thread = threading.Thread(
                target=self._monitor, daemon=True
            )
            self._monitor_thread.start()

            return {"ok": True, "source": source["name"]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_music(self, music_concat_file):
        """Update the music playlist. Requires a source switch to take effect."""
        self._music_concat_file = music_concat_file

    def get_status(self):
        """Return current stream status."""
        uptime = 0
        source_time = 0
        if self._start_time and self.status == "live":
            uptime = int(time.time() - self._start_time)
        if self._source_start_time and self.status == "live":
            source_time = int(time.time() - self._source_start_time)

        return {
            "status": self.status,
            "uptime_sec": uptime,
            "uptime_str": self._format_uptime(uptime),
            "source_time_sec": source_time,
            "source_time_str": self._format_uptime(source_time),
            "current_source": self.current_source.get("name") if self.current_source else None,
            "current_source_id": self.current_source.get("id") if self.current_source else None,
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "error": self._error_msg,
        }

    def _build_ffmpeg_cmd(self, source_url, music_concat_file,
                          overlay_path, stream_key):
        """Build the FFmpeg command for webcam + music + overlay → RTMP."""
        cmd = ["ffmpeg"]

        # Input 0: Webcam source
        if source_url.startswith(("http://", "https://")):
            cmd += ["-reconnect", "1", "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5"]
        cmd += ["-i", source_url]

        # Input 1: Music playlist (concat demuxer, looped)
        cmd += ["-f", "concat", "-safe", "0", "-stream_loop", "-1",
                "-i", music_concat_file]

        # Input 2: Overlay PNG (looped, atomically updated on disk)
        cmd += ["-stream_loop", "-1", "-i", overlay_path]

        # Filter complex: scale webcam to 1080p, apply overlay
        cmd += [
            "-filter_complex",
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30[webcam];"
            "[webcam][2:v]overlay=0:0:format=auto,format=yuv420p[vout]",
        ]

        # Map: composited video + music audio (discard webcam audio)
        cmd += ["-map", "[vout]", "-map", "1:a"]

        # Video encoding
        cmd += ["-c:v", "libx264", "-preset", "veryfast",
                "-b:v", "3000k", "-maxrate", "3000k", "-bufsize", "6000k",
                "-g", "60"]

        # Audio encoding
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"]

        # Output to YouTube RTMP
        cmd += ["-f", "flv",
                f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"]

        return cmd

    def _monitor(self):
        """Background thread: watch for process exit."""
        if not self.process:
            return
        returncode = self.process.wait()
        if returncode != 0 and self.status == "live":
            try:
                stderr = self.process.stderr.read().decode(errors="replace")[-500:]
            except Exception:
                stderr = ""
            self._error_msg = f"FFmpeg exited with code {returncode}: {stderr}"
            self.status = "error"
        elif self.status != "stopped":
            self.status = "stopped"

    @staticmethod
    def _format_uptime(seconds):
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return f"{h}h {m}m"
