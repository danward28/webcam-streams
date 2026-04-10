"""Webcam Streams — Web Application."""

import json
import os
import queue
import time
from pathlib import Path

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, url_for)

import config
import library
import overlays
import webcam_sources
from music_manager import MusicManager, GENRES
from music_styles import get_styles_for_generator
from source_cycler import SourceCycler
from stream_manager import StreamManager
from worker import GenerationWorker

app = Flask(__name__)
app.secret_key = config.get("FLASK_SECRET_KEY", "webcam-stream-secret-key")

# Global instances
worker = GenerationWorker()
stream_mgr = StreamManager()
music_mgr = MusicManager()
source_cycler = SourceCycler(stream_mgr,
                             cycle_interval_sec=config.get_all()["CYCLE_INTERVAL"])
overlay_scheduler = overlays.OverlayScheduler()
health_checker = webcam_sources.HealthChecker()

# Set default genre from theme config
music_mgr.current_genre = config.get_all()["DEFAULT_GENRE"]


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    theme = config.get_theme()
    return render_template("dashboard.html",
                           stream=stream_mgr.get_status(),
                           cycler=source_cycler.get_status(),
                           music=music_mgr.get_status(),
                           current_task=worker.current_task,
                           queue_size=worker.queue_size,
                           history=list(reversed(worker.history[-10:])),
                           lib_stats=library.stats(),
                           source_stats=webcam_sources.stats(),
                           theme=theme)


# ── Webcam Sources ───────────────────────────────────────────────────────────

@app.route("/sources")
def sources_page():
    sources = webcam_sources.list_sources()
    return render_template("sources.html",
                           sources=sources,
                           stats=webcam_sources.stats(),
                           theme=config.get_theme())


@app.route("/sources", methods=["POST"])
def sources_add():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    source_type = request.form.get("type", "youtube_live")
    category = request.form.get("category", "")
    notes = request.form.get("notes", "")

    if not name or not url:
        return redirect(url_for("sources_page"))

    webcam_sources.add_source(name, url, source_type, category, notes)
    return redirect(url_for("sources_page"))


@app.route("/sources/toggle/<source_id>", methods=["POST"])
def sources_toggle(source_id):
    webcam_sources.toggle_source(source_id)
    return redirect(url_for("sources_page"))


@app.route("/sources/delete/<source_id>", methods=["POST"])
def sources_delete(source_id):
    webcam_sources.remove_source(source_id)
    return redirect(url_for("sources_page"))


@app.route("/sources/test", methods=["POST"])
def sources_test():
    url = request.form.get("url", "").strip()
    source_type = request.form.get("type", "youtube_live")
    ok, info = webcam_sources.test_source(url, source_type)
    return jsonify({"ok": ok, "info": info})


@app.route("/sources/health-check", methods=["POST"])
def sources_health_check():
    results = webcam_sources.health_check_all()
    return redirect(url_for("sources_page"))


# ── Music Library ────────────────────────────────────────────────────────────

@app.route("/music")
def music_page():
    genre_filter = request.args.get("genre", "")
    assets = library.list_assets(
        asset_type="music",
        genre=genre_filter if genre_filter else None,
    )
    return render_template("music.html",
                           assets=assets,
                           stats=library.stats(),
                           music=music_mgr.get_status(),
                           genres=GENRES,
                           ace_step_styles=get_styles_for_generator("ace_step"),
                           musicgen_styles=get_styles_for_generator("musicgen"),
                           suno_styles=get_styles_for_generator("suno"),
                           current_genre=genre_filter,
                           theme=config.get_theme())


@app.route("/music/upload", methods=["POST"])
def music_upload():
    if "file" not in request.files or not request.files["file"].filename:
        return redirect(url_for("music_page"))

    f = request.files["file"]
    genre = request.form.get("genre", "instrumental")
    title = request.form.get("title", "").strip() or f.filename

    # Save to temp, then add to library
    output_dir = library.PROJECT_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    temp_path = output_dir / f.filename
    f.save(str(temp_path))

    library.add(
        str(temp_path),
        title=title,
        genre=genre,
        generator="upload",
        asset_type="music",
    )
    return redirect(url_for("music_page"))


@app.route("/music/genre", methods=["POST"])
def music_set_genre():
    genre = request.form.get("genre", "instrumental")
    music_mgr.set_genre(genre)
    return redirect(url_for("music_page"))


@app.route("/music/generate", methods=["POST"])
def music_generate():
    generator = request.form.get("generator", "ace_step")
    style_id = request.form.get("style_id", "")
    worker.enqueue(generator, extra={"style_id": style_id})
    return redirect(url_for("dashboard"))


@app.route("/music/toggle/<asset_id>", methods=["POST"])
def music_toggle(asset_id):
    library.toggle(asset_id)
    return redirect(url_for("music_page"))


@app.route("/music/delete/<asset_id>", methods=["POST"])
def music_delete(asset_id):
    library.remove(asset_id)
    return redirect(url_for("music_page"))


# ── Overlays ─────────────────────────────────────────────────────────────────

def _overlay_limits():
    return {
        "max_text_banner": overlays.MAX_TEXT_BANNER_CHARS,
        "max_image_text": overlays.MAX_IMAGE_TEXT_CHARS,
        "min_image_px": overlays.MIN_IMAGE_WIDTH,
        "max_image_mb": overlays.MAX_IMAGE_FILE_SIZE // (1024 * 1024),
        "min_duration": overlays.MIN_DURATION_SEC,
        "max_duration": overlays.MAX_DURATION_SEC,
        "min_interval": overlays.MIN_INTERVAL_SEC,
        "max_interval": overlays.MAX_INTERVAL_SEC,
    }


@app.route("/overlays")
def overlays_page():
    return render_template("overlays.html",
                           overlays=overlays.list_overlays(),
                           overlay_styles=overlays.OVERLAY_STYLES,
                           overlay_limits=_overlay_limits(),
                           scheduler_running=overlay_scheduler.running)


@app.route("/overlays", methods=["POST"])
def overlays_create():
    otype = request.form.get("type", "text_banner")
    text = request.form.get("text", "")
    position = request.form.get("position", "bottom")
    style = request.form.get("style", "elegant_gold")

    try:
        duration = int(request.form.get("duration_sec", 15))
    except (ValueError, TypeError):
        duration = 15
    try:
        interval = int(request.form.get("interval_sec", 300))
    except (ValueError, TypeError):
        interval = 300

    image = ""
    if "image" in request.files and request.files["image"].filename:
        f = request.files["image"]
        ok, err = overlays.validate_image(f)
        if not ok:
            return render_template("overlays.html",
                                   overlays=overlays.list_overlays(),
                                   overlay_styles=overlays.OVERLAY_STYLES,
                                   overlay_limits=_overlay_limits(),
                                   scheduler_running=overlay_scheduler.running,
                                   error=err)
        image = overlays.save_uploaded_image(f)

    overlays.create_overlay(otype, text=text, image=image,
                            position=position, duration_sec=duration,
                            interval_sec=interval, style=style)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/toggle/<overlay_id>", methods=["POST"])
def overlays_toggle(overlay_id):
    overlays.toggle_overlay(overlay_id)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/delete/<overlay_id>", methods=["POST"])
def overlays_delete(overlay_id):
    overlays.delete_overlay(overlay_id)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/preview/<overlay_id>")
def overlays_preview(overlay_id):
    overlay = overlays.get_overlay(overlay_id)
    if not overlay:
        return "Not found", 404
    img = overlays.render_overlay(overlay)
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/overlays/live-preview")
def overlays_live_preview():
    overlay = {
        "type": request.args.get("type", "text_banner"),
        "text": request.args.get("text", "Preview text here"),
        "position": request.args.get("position", "bottom"),
        "style": request.args.get("style", "elegant_gold"),
        "image": "",
    }
    img = overlays.render_overlay(overlay)
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/overlays/scheduler/start", methods=["POST"])
def overlays_scheduler_start():
    overlay_scheduler.start()
    return redirect(url_for("overlays_page"))


@app.route("/overlays/scheduler/stop", methods=["POST"])
def overlays_scheduler_stop():
    overlay_scheduler.stop()
    return redirect(url_for("overlays_page"))


# ── Stream Control ───────────────────────────────────────────────────────────

@app.route("/stream/start", methods=["POST"])
def stream_start():
    key = request.form.get("stream_key") or config.get("YOUTUBE_STREAM_KEY", "")
    if not key:
        return redirect(url_for("settings_page"))

    # Get first available source
    sources = webcam_sources.get_active_playlist()
    if not sources:
        return render_template("dashboard.html",
                               stream=stream_mgr.get_status(),
                               cycler=source_cycler.get_status(),
                               music=music_mgr.get_status(),
                               current_task=worker.current_task,
                               queue_size=worker.queue_size,
                               history=list(reversed(worker.history[-10:])),
                               lib_stats=library.stats(),
                               source_stats=webcam_sources.stats(),
                               theme=config.get_theme(),
                               error="No webcam sources available")

    # Build music playlist
    music_file = music_mgr.build_playlist()
    if not music_file:
        return render_template("dashboard.html",
                               stream=stream_mgr.get_status(),
                               cycler=source_cycler.get_status(),
                               music=music_mgr.get_status(),
                               current_task=worker.current_task,
                               queue_size=worker.queue_size,
                               history=list(reversed(worker.history[-10:])),
                               lib_stats=library.stats(),
                               source_stats=webcam_sources.stats(),
                               theme=config.get_theme(),
                               error="No music tracks in library")

    source = sources[0]
    result = stream_mgr.start(key, source, music_file)
    if not result["ok"]:
        return render_template("dashboard.html",
                               stream=stream_mgr.get_status(),
                               cycler=source_cycler.get_status(),
                               music=music_mgr.get_status(),
                               current_task=worker.current_task,
                               queue_size=worker.queue_size,
                               history=list(reversed(worker.history[-10:])),
                               lib_stats=library.stats(),
                               source_stats=webcam_sources.stats(),
                               theme=config.get_theme(),
                               error=result["error"])

    # Start source cycling
    source_cycler.start(sources)

    return redirect(url_for("dashboard"))


@app.route("/stream/stop", methods=["POST"])
def stream_stop():
    source_cycler.stop()
    stream_mgr.stop()
    return redirect(url_for("dashboard"))


@app.route("/stream/skip", methods=["POST"])
def stream_skip():
    """Skip to the next webcam source."""
    source_cycler.skip()
    return redirect(url_for("dashboard"))


@app.route("/stream/status")
def stream_status():
    status = stream_mgr.get_status()
    status["cycler"] = source_cycler.get_status()
    status["music"] = music_mgr.get_status()
    return jsonify(status)


# ── Settings ─────────────────────────────────────────────────────────────────

@app.route("/settings")
def settings_page():
    return render_template("settings.html",
                           config=config.get_all(),
                           theme=config.get_theme())


@app.route("/settings", methods=["POST"])
def settings_save():
    for key in ["YOUTUBE_STREAM_KEY", "ANTHROPIC_API_KEY", "SUNO_API_KEY"]:
        val = request.form.get(key, "").strip()
        if val:
            config.set_runtime(key, val)
            os.environ[key] = val

    # Cycle interval
    interval = request.form.get("CYCLE_INTERVAL", "")
    if interval:
        try:
            config.set_runtime("CYCLE_INTERVAL", int(interval))
            source_cycler.set_interval(int(interval))
        except ValueError:
            pass

    # Default genre
    genre = request.form.get("DEFAULT_GENRE", "")
    if genre:
        config.set_runtime("DEFAULT_GENRE", genre)
        music_mgr.set_genre(genre)

    return redirect(url_for("settings_page"))


# ── SSE Events ───────────────────────────────────────────────────────────────

@app.route("/events")
def events():
    def stream():
        q = queue.Queue()
        worker.register_callback(lambda evt: q.put(evt))

        try:
            while True:
                try:
                    evt = q.get(timeout=15)
                    yield f"data: {json.dumps(evt, default=str)}\n\n"
                except queue.Empty:
                    status = stream_mgr.get_status()
                    status["current_task"] = worker.current_task
                    status["queue_size"] = worker.queue_size
                    status["cycler"] = source_cycler.get_status()
                    status["music"] = music_mgr.get_status()
                    yield f"data: {json.dumps({'type': 'heartbeat', **status}, default=str)}\n\n"
        finally:
            worker.unregister_callback(lambda evt: q.put(evt))

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ── Startup ──────────────────────────────────────────────────────────────────

def create_app():
    """Factory for Gunicorn."""
    library._ensure_dirs()
    webcam_sources._ensure_dirs()
    overlays.init()
    worker.start()
    health_checker.start()
    return app


# Start worker when running directly
worker.start()
health_checker.start()

if __name__ == "__main__":
    library._ensure_dirs()
    webcam_sources._ensure_dirs()
    overlays.init()
    port = int(config.get("FLASK_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
