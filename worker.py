"""Background music generation worker thread."""

import os
import queue
import subprocess
import threading
import traceback
from pathlib import Path
from uuid import uuid4

import library
from music_styles import get_style, get_styles_for_generator


class GenerationWorker:
    """Processes music generation tasks one at a time in a background thread."""

    def __init__(self):
        self.task_queue = queue.Queue()
        self.current_task = None
        self.history = []
        self._thread = None
        self._stop = threading.Event()
        self._callbacks = []
        self._lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def unregister_callback(self, cb):
        try:
            self._callbacks.remove(cb)
        except ValueError:
            pass

    def _notify(self, event):
        for cb in list(self._callbacks):
            try:
                cb(event)
            except Exception:
                pass

    def enqueue(self, generator, **kwargs):
        """Add a music generation task to the queue."""
        task = {
            "id": uuid4().hex[:8],
            "generator": generator,
            "status": "queued",
            "progress": "",
            "extra": kwargs.get("extra", {}),
        }
        self.task_queue.put(task)
        self._notify({"type": "task_queued", "task": task})
        return task

    @property
    def queue_size(self):
        return self.task_queue.qsize()

    @property
    def pending_tasks(self):
        return list(self.task_queue.queue)

    def _run(self):
        while not self._stop.is_set():
            try:
                task = self.task_queue.get(timeout=1)
            except queue.Empty:
                continue

            self.current_task = task
            task["status"] = "running"
            self._notify({"type": "task_started", "task": task})

            try:
                result = self._execute(task)
                if result:
                    task["status"] = "done"
                    task["result"] = result
                else:
                    task["status"] = "failed"
                    task["error"] = "Generation returned no output"
            except Exception as e:
                task["status"] = "failed"
                task["error"] = str(e)
                traceback.print_exc()

            with self._lock:
                self.history.append(task)
                if len(self.history) > 50:
                    self.history = self.history[-50:]

            self.current_task = None
            self._notify({"type": "task_complete", "task": task})

    def _execute(self, task):
        generator = task["generator"]

        def on_progress(step, detail=""):
            task["progress"] = f"{step}: {detail}"
            self._notify({"type": "task_progress", "task": task})

        if generator == "ace_step":
            return self._run_ace_step(task, on_progress)
        elif generator == "musicgen":
            return self._run_musicgen(task, on_progress)
        elif generator == "suno":
            return self._run_suno(task, on_progress)
        else:
            raise ValueError(f"Unknown generator: {generator}")

    def _run_ace_step(self, task, on_progress):
        from generate_music import generate_track_ace_step, convert_to_aac

        style_id = task.get("extra", {}).get("style_id", "")
        style = get_style("ace_step", style_id)
        if not style:
            styles = get_styles_for_generator("ace_step")
            style = styles[0] if styles else None
        if not style:
            return None

        on_progress("generating", f"ACE-Step: {style['label']}")
        output_dir = str(library.PROJECT_DIR / "output")
        os.makedirs(output_dir, exist_ok=True)
        output_wav = os.path.join(output_dir, f"{style['id']}_{task['id']}.wav")

        duration = int(task.get("extra", {}).get("duration", 360))
        success = generate_track_ace_step(style, output_wav, duration)
        if not success:
            return None

        on_progress("converting", "WAV to AAC...")
        final = convert_to_aac(output_wav)

        on_progress("done", "Adding to library")
        entry = library.add(
            final,
            title=style["label"],
            genre=style.get("genre", "instrumental"),
            generator="ace_step",
            asset_type="music",
        )
        return entry

    def _run_musicgen(self, task, on_progress):
        from generate_music_musicgen import (
            check_musicgen, generate_chunk,
            concatenate_audio, save_audio, CHUNK_SECONDS
        )

        if not check_musicgen():
            raise RuntimeError("MusicGen (audiocraft) not installed")

        import torch
        from audiocraft.models import MusicGen

        style_id = task.get("extra", {}).get("style_id", "")
        style = get_style("musicgen", style_id)
        if not style:
            styles = get_styles_for_generator("musicgen")
            style = styles[0] if styles else None
        if not style:
            return None

        model_size = task.get("extra", {}).get("model", "medium")
        num_chunks = int(task.get("extra", {}).get("chunks", 15))

        on_progress("loading_model", f"MusicGen {model_size}...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = MusicGen.get_pretrained(f"facebook/musicgen-{model_size}")
        model = model.to(device)

        on_progress("generating", f"{style['label']} (0/{num_chunks} chunks)")
        chunks = []
        for i in range(num_chunks):
            on_progress("generating", f"{style['label']} ({i+1}/{num_chunks} chunks)")
            chunk = generate_chunk(model, style["prompt"], CHUNK_SECONDS)
            chunks.append(chunk)

        on_progress("merging", "Concatenating chunks...")
        full_audio = concatenate_audio(chunks, model.sample_rate)

        output_dir = str(library.PROJECT_DIR / "output")
        os.makedirs(output_dir, exist_ok=True)
        output_wav = os.path.join(output_dir, f"{style['id']}_{task['id']}.wav")
        save_audio(full_audio, model.sample_rate, output_wav)

        on_progress("converting", "WAV to AAC...")
        aac_path = output_wav.replace(".wav", ".aac")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", output_wav, "-c:a", "aac", "-b:a", "128k", aac_path],
            capture_output=True
        )
        final = aac_path if result.returncode == 0 else output_wav
        if result.returncode == 0 and os.path.exists(output_wav):
            os.remove(output_wav)

        entry = library.add(
            final,
            title=style["label"],
            genre=style.get("genre", "instrumental"),
            generator="musicgen",
            asset_type="music",
        )
        return entry

    def _run_suno(self, task, on_progress):
        from generate_music_suno import (
            generate_with_suno, poll_for_audio, download_audio
        )
        import config

        api_key = config.get("SUNO_API_KEY", "")
        if not api_key:
            raise RuntimeError("SUNO_API_KEY not configured")

        style_id = task.get("extra", {}).get("style_id", "")
        style = get_style("suno", style_id)
        if not style:
            styles = get_styles_for_generator("suno")
            style = styles[0] if styles else None
        if not style:
            return None

        on_progress("requesting", f"Suno: {style['title']}")
        result = generate_with_suno(style, api_key)
        if not result:
            return None

        tasks = result if isinstance(result, list) else [result]
        task_data = tasks[0]
        task_id = task_data.get("id") or task_data.get("clip_id")
        if not task_id:
            return None

        on_progress("polling", "Waiting for Suno to finish...")
        audio_url = poll_for_audio(task_id, api_key)
        if not audio_url:
            return None

        output_dir = str(library.PROJECT_DIR / "output")
        os.makedirs(output_dir, exist_ok=True)
        output_mp3 = os.path.join(output_dir, f"{style['id']}_{task['id']}.mp3")

        on_progress("downloading", "Downloading audio...")
        if not download_audio(audio_url, output_mp3):
            return None

        entry = library.add(
            output_mp3,
            title=style["title"],
            genre=style.get("genre", "instrumental"),
            generator="suno",
            asset_type="music",
        )
        return entry
