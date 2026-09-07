import os
import sys
import socket
import threading
import json
import logging
import shutil
from typing import Optional, Dict, Any
from io import BytesIO
import bottle
from bottle import Bottle, request, response, static_file
from PIL import Image

# Import core modules
from core.downloader import MediaDownloader
from core.metadata import fetch_metadata

logger = logging.getLogger(__name__)


class VantrixServer:
    def __init__(self, download_dir: Optional[str] = None, port: int = 8080, host: str = "127.0.0.1"):
        self.download_dir = download_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.port = port
        self.host = host
        self.ip = host
        self.downloader = MediaDownloader(output_dir=self.download_dir)
        self.app = Bottle()
        self.server_thread = None
        self.is_running = False

        # Multi-task state tracking
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.active_downloaders: Dict[str, MediaDownloader] = {}

        self._setup_routes()

    @property
    def url(self) -> str:
        return f"http://{self.ip}:{self.port}"

    def _setup_routes(self):
        @self.app.hook('after_request')
        def enable_cors():
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Accept'

        self.app.route("/", method="GET", callback=self.handle_index)
        self.app.route("/api/info", method="GET", callback=self.handle_api_info)
        self.app.route("/api/analyze", method="POST", callback=self.handle_api_analyze)
        self.app.route("/api/download", method="POST", callback=self.handle_api_download)
        self.app.route("/api/progress", method="GET", callback=self.handle_api_progress)
        self.app.route("/api/cancel", method="POST", callback=self.handle_api_cancel)
        self.app.route("/api/delete", method="POST", callback=self.handle_api_delete)
        self.app.route("/api/library", method="GET", callback=self.handle_api_library)
        self.app.route("/stream/<filename:path>", method="GET", callback=self.handle_stream)
        self.app.route("/download/<filename:path>", method="GET", callback=self.handle_file_download)
        self.app.route("/thumbnail/<filename:path>", method="GET", callback=self.handle_thumbnail)
        self.app.route("/logo.png", method="GET", callback=self.handle_logo)
        self.app.route("/favicon.ico", method="GET", callback=self.handle_favicon)

    def handle_logo(self):
        ui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_ui")
        return static_file("logo.png", root=ui_dir, mimetype="image/png")

    def handle_favicon(self):
        ui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_ui")
        return static_file("favicon.ico", root=ui_dir, mimetype="image/x-icon")

    def handle_index(self):
        ui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_ui", "index.html")
        if os.path.exists(ui_path):
            with open(ui_path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h3>Vantrix-Downloader UI not found.</h3>"

    def handle_api_info(self):
        response.content_type = "application/json"
        
        # Calculate disk free space
        free_gb = 0
        total_gb = 0
        try:
            total, used, free = shutil.disk_usage(self.download_dir)
            free_gb = round(free / (1024 ** 3), 1)
            total_gb = round(total / (1024 ** 3), 1)
        except Exception:
            pass

        return json.dumps({
            "url": self.url,
            "ip": self.ip,
            "port": self.port,
            "download_dir": self.download_dir,
            "free_storage_gb": free_gb,
            "total_storage_gb": total_gb,
            "active_tasks_count": sum(1 for t in self.tasks.values() if t.get("status") == "downloading")
        })

    def handle_api_analyze(self):
        response.content_type = "application/json"
        data = request.json or {}
        url = data.get("url", "").strip()
        if not url:
            response.status = 400
            return json.dumps({"success": False, "error": "URL parameter is required"})

        try:
            meta = fetch_metadata(url)
            
            # Map resolutions to user-friendly options
            resolutions = meta.get("resolutions", ["Best Available"])
            has_4k = any("4K" in r or "2160p" in r for r in resolutions)
            has_1080p = any("1080p" in r for r in resolutions)
            has_720p = any("720p" in r for r in resolutions)

            # Try to extract direct stream URL if possible for instant player preview
            preview_stream_url = None
            raw_info = meta.get("raw_info", {})
            if raw_info:
                # Find best direct video/audio URL for quick preview
                direct_url = raw_info.get("url")
                if direct_url and (direct_url.startswith("http://") or direct_url.startswith("https://")):
                    preview_stream_url = direct_url

            return json.dumps({
                "success": True,
                "title": meta.get("title", "Unknown Media"),
                "uploader": meta.get("uploader", "Unknown Creator"),
                "duration": meta.get("duration", "--:--"),
                "thumbnail_url": meta.get("thumbnail_url"),
                "is_playlist": meta.get("is_playlist", False),
                "max_audio_channels": meta.get("max_audio_channels", 2),
                "resolutions": resolutions,
                "has_4k": has_4k,
                "has_1080p": has_1080p,
                "has_720p": has_720p,
                "preview_url": preview_stream_url or meta.get("thumbnail_url") or "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
            })

        except Exception as e:
            logger.error(f"Analysis error for {url}: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def handle_api_download(self):
        response.content_type = "application/json"
        data = request.json or {}
        url = data.get("url", "").strip()
        raw_quality = data.get("quality", "Best Available")
        format_ext = data.get("format", "mp4").lower()
        media_type = data.get("type", "video").lower()

        if not url:
            response.status = 400
            return json.dumps({"success": False, "error": "URL is required"})

        # Normalize quality strings
        quality_map = {
            "4k": "4K Ultra HD (2160p)",
            "1440p": "2K Quad HD (1440p)",
            "1080p": "1080p Full HD (60fps)",
            "720p": "720p HD",
            "480p": "480p SD",
            "360p": "360p",
            "best": "Best Available",
            "flac": "Lossless FLAC (Studio Quality)",
            "wav": "Lossless WAV (Uncompressed PCM)",
            "dolby": "Dolby Digital AC3 (5.1 Surround / 640 kbps)",
            "mp3": "MP3 (320 kbps Maximum Quality)",
            "aac": "AAC / M4A (256 kbps)",
            "m4a": "AAC / M4A (256 kbps)",
            "opus": "OPUS (Next-Gen Hi-Fi)",
        }
        quality = quality_map.get(raw_quality.lower(), raw_quality)

        # Detect media type from requested format or quality
        audio_keywords = ["flac", "wav", "mp3", "m4a", "opus", "ogg", "dolby", "aac", "ac3"]

        if format_ext in audio_keywords or "audio" in media_type or raw_quality.lower() in audio_keywords:
            media_type = "audio"
            # Auto-align format_ext with audio selection if container is still video default
            if format_ext in ["mp4", "mkv", "webm", ""]:
                if raw_quality.lower() in ["flac", "wav", "mp3", "opus"]:
                    format_ext = raw_quality.lower()
                elif raw_quality.lower() in ["aac", "m4a"]:
                    format_ext = "m4a"
                elif raw_quality.lower() in ["dolby", "ac3"]:
                    format_ext = "ac3"
                else:
                    format_ext = "mp3"
        else:
            media_type = "video"
            if format_ext not in ["mp4", "mkv", "webm"]:
                format_ext = "mp4"


        task_id = str(len(self.tasks) + 1)
        downloader = MediaDownloader(output_dir=self.download_dir)
        self.active_downloaders[task_id] = downloader

        self.tasks[task_id] = {
            "id": task_id,
            "url": url,
            "name": "Initializing download...",
            "quality": quality,
            "format": format_ext,
            "type": media_type,
            "status": "downloading",
            "percent": 0.0,
            "speed": "-- MB/s",
            "eta": "--:--",
            "size": "--",
            "file_path": None,
            "error": None
        }

        def progress_cb(d: dict):
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = d.get("status", "downloading")
                self.tasks[task_id]["percent"] = round(d.get("percent", 0.0), 1)
                self.tasks[task_id]["speed"] = d.get("speed", "-- MB/s")
                self.tasks[task_id]["eta"] = d.get("eta", "--:--")
                self.tasks[task_id]["size"] = d.get("size", "--")
                if d.get("filename"):
                    self.tasks[task_id]["name"] = d.get("filename")

        def worker():
            res = downloader.download(
                url=url,
                media_type=media_type,
                quality=quality,
                format_ext=format_ext,
                progress_callback=progress_cb
            )
            if task_id in self.tasks:
                if res.get("cancelled"):
                    self.tasks[task_id]["status"] = "cancelled"
                elif res.get("success"):
                    self.tasks[task_id]["status"] = "finished"
                    self.tasks[task_id]["percent"] = 100.0
                    self.tasks[task_id]["file_path"] = res.get("file_path")
                    self.tasks[task_id]["name"] = os.path.basename(res.get("file_path", "Media"))
                else:
                    self.tasks[task_id]["status"] = "error"
                    self.tasks[task_id]["error"] = res.get("error", "Download failed")

            self.active_downloaders.pop(task_id, None)

        threading.Thread(target=worker, daemon=True).start()
        return json.dumps({"success": True, "task_id": task_id, "message": "Download started"})

    def handle_api_progress(self):
        response.content_type = "application/json"
        # Calculate combined speed for top bar
        total_speed_mb = 0.0
        for t in self.tasks.values():
            if t.get("status") == "downloading":
                sp_str = t.get("speed", "")
                if "MB/s" in sp_str:
                    try:
                        total_speed_mb += float(sp_str.replace("MB/s", "").strip())
                    except ValueError:
                        pass

        speed_display = f"{round(total_speed_mb, 1)} MB/s" if total_speed_mb > 0 else "0.0 MB/s"

        return json.dumps({
            "tasks": self.tasks,
            "total_speed": speed_display,
            "active_count": sum(1 for t in self.tasks.values() if t.get("status") == "downloading"),
            "completed_count": sum(1 for t in self.tasks.values() if t.get("status") == "finished")
        })

    def handle_api_cancel(self):
        response.content_type = "application/json"
        data = request.json or {}
        task_id = str(data.get("task_id", ""))
        downloader = self.active_downloaders.get(task_id)
        if downloader:
            downloader.cancel()
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "cancelled"
            return json.dumps({"success": True, "message": "Cancelled"})
        return json.dumps({"success": False, "error": "Task not found or already finished"})

    def handle_api_delete(self):
        response.content_type = "application/json"
        data = request.json or {}
        filename = data.get("filename", "").strip()
        if not filename:
            response.status = 400
            return json.dumps({"success": False, "error": "Filename is required"})

        clean_filename = os.path.basename(filename)
        target_path = os.path.join(self.download_dir, clean_filename)
        if not os.path.exists(target_path):
            return json.dumps({"success": False, "error": "File not found on disk"})

        try:
            os.remove(target_path)

            # Also remove cached thumbnail if present
            base_name, _ = os.path.splitext(clean_filename)
            thumb_dir = os.path.join(self.download_dir, ".thumbnails")
            cached_thumb = os.path.join(thumb_dir, f"{base_name}.jpg")
            if os.path.exists(cached_thumb):
                try:
                    os.remove(cached_thumb)
                except Exception:
                    pass

            return json.dumps({"success": True, "message": f"Successfully deleted {clean_filename}"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def handle_thumbnail(self, filename: str):
        clean_filename = os.path.basename(filename)
        base_name, ext = os.path.splitext(clean_filename)
        thumb_dir = os.path.join(self.download_dir, ".thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        cached_thumb = os.path.join(thumb_dir, f"{base_name}.jpg")

        # 1. Check if cached thumbnail exists
        if os.path.exists(cached_thumb):
            return static_file(f"{base_name}.jpg", root=thumb_dir)

        # 2. Try to extract from the source media file if present on disk
        media_path = os.path.join(self.download_dir, clean_filename)
        if not os.path.exists(media_path):
            for cand in os.listdir(self.download_dir):
                if cand.startswith(base_name) and os.path.isfile(os.path.join(self.download_dir, cand)):
                    media_path = os.path.join(self.download_dir, cand)
                    break

        if os.path.exists(media_path):
            ext_lower = os.path.splitext(media_path)[1].lower()
            try:
                # Audio extraction via mutagen
                if ext_lower in [".mp3", ".flac", ".m4a"]:
                    import mutagen
                    audio_file = mutagen.File(media_path)
                    if audio_file:
                        art_data = None
                        if hasattr(audio_file, 'pictures') and audio_file.pictures:
                            art_data = audio_file.pictures[0].data
                        elif 'APIC:' in audio_file:
                            art_data = audio_file['APIC:'].data
                        elif hasattr(audio_file, 'tags') and audio_file.tags:
                            for key in ['covr', 'APIC']:
                                if key in audio_file.tags:
                                    val = audio_file.tags[key]
                                    art_data = val[0] if isinstance(val, list) else getattr(val, 'data', val)
                                    break
                        if art_data:
                            from PIL import Image
                            img = Image.open(BytesIO(art_data)).convert("RGB")
                            img.save(cached_thumb, "JPEG", quality=90)
                            return static_file(f"{base_name}.jpg", root=thumb_dir)

                # Video extraction via FFmpeg frame capture
                elif ext_lower in [".mp4", ".mkv", ".webm", ".mov"]:
                    from core.ffmpeg_helper import get_ffmpeg_path
                    import subprocess
                    ffmpeg_bin = get_ffmpeg_path()
                    if ffmpeg_bin:
                        subprocess.run([
                            ffmpeg_bin, "-y", "-ss", "00:00:01",
                            "-i", media_path, "-vframes", "1",
                            "-q:v", "2", cached_thumb
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                        if os.path.exists(cached_thumb):
                            return static_file(f"{base_name}.jpg", root=thumb_dir)
            except Exception as e:
                logger.debug(f"Thumbnail extraction failed for {media_path}: {e}")

        # 3. Fallback: generate a stylish SVG placeholder thumbnail
        response.content_type = "image/svg+xml"
        is_audio = ext.lower() in [".flac", ".wav", ".mp3", ".m4a", ".opus", ".ac3"]
        bg_color_1 = "#7c3aed" if is_audio else "#0284c7"
        bg_color_2 = "#4f46e5" if is_audio else "#0f172a"
        icon_label = "AUDIO" if is_audio else "VIDEO"
        title_disp = (base_name[:24] + "...") if len(base_name) > 24 else base_name
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg_color_1}"/>
      <stop offset="100%" stop-color="{bg_color_2}"/>
    </linearGradient>
  </defs>
  <rect width="320" height="180" rx="16" fill="url(#bg)"/>
  <circle cx="160" cy="75" r="32" fill="rgba(255,255,255,0.15)"/>
  <polygon points="152,60 174,75 152,90" fill="#ffffff"/>
  <text x="160" y="130" fill="#ffffff" font-family="sans-serif" font-size="12" font-weight="bold" text-anchor="middle">{title_disp}</text>
  <text x="160" y="150" fill="rgba(255,255,255,0.7)" font-family="sans-serif" font-size="10" text-anchor="middle">{icon_label} • VANTRIX-DOWNLOADER</text>
</svg>'''

    def handle_api_library(self):
        response.content_type = "application/json"
        files = []
        valid_exts = {".mp4", ".mkv", ".webm", ".flac", ".wav", ".mp3", ".m4a", ".opus", ".ac3"}
        audio_exts = {".flac", ".wav", ".mp3", ".m4a", ".opus", ".ac3"}

        if os.path.exists(self.download_dir):
            for name in sorted(os.listdir(self.download_dir), reverse=True):
                ext = os.path.splitext(name)[1].lower()
                if ext in valid_exts:
                    full_path = os.path.join(self.download_dir, name)
                    if os.path.isfile(full_path):
                        size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 2)
                        size_str = f"{size_mb} MB" if size_mb < 1024 else f"{round(size_mb/1024, 2)} GB"
                        if size_mb < 0.1:
                            size_str = f"{round(os.path.getsize(full_path) / 1024, 1)} KB"

                        is_aud = ext in audio_exts
                        m_type = "audio" if is_aud else "video"


                        files.append({
                            "name": name,
                            "size": size_str,
                            "type": m_type,
                            "ext": ext.lstrip(".").upper(),
                            "stream_url": f"/stream/{name}",
                            "download_url": f"/download/{name}",
                            "thumbnail_url": f"/thumbnail/{name}"
                        })
        return json.dumps({"files": files})

    def handle_stream(self, filename: str):
        # bottle's static_file natively handles Range headers for media seeking/scrubbing
        return static_file(filename, root=self.download_dir)

    def handle_file_download(self, filename: str):
        # Triggers direct download on the local Windows machine
        return static_file(filename, root=self.download_dir, download=True)

    def start(self):
        if self.is_running:
            return
        self.is_running = True

        def run_server():
            try:
                bottle.run(self.app, host=self.host, port=self.port, quiet=True)
            except Exception as e:
                logger.error(f"Media server error: {e}")
                self.is_running = False

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()


# Backward-compatible aliases
LocalMediaServer = VantrixServer
MobileServer = VantrixServer
WindowsMediaServer = VantrixServer
