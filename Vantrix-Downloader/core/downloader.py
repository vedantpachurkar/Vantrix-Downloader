import os
import re
import sys
import glob
import shutil
import logging
import subprocess
from io import BytesIO
from typing import Callable, Optional, Dict, Any
import requests
from PIL import Image
import yt_dlp
from .ffmpeg_helper import get_ffmpeg_path

logger = logging.getLogger(__name__)




class DownloadCancelledException(Exception):
    """Raised when user cancels download."""
    pass


def is_file_locked(filepath: str) -> bool:
    """
    Reliably checks if a file exists and is currently locked or in-use by
    another application (media player, Groove, VLC, OneDrive, Explorer).
    On Windows, attempting to rename a file to itself fails with WinError 32 or 5
    if any process holds a non-shared lock.
    """
    if not os.path.exists(filepath):
        return False
    try:
        os.rename(filepath, filepath)
        return False
    except OSError:
        return True


def get_safe_base_template(output_dir: str, title: str, video_id: str, extensions: list[str]) -> str:
    """
    Returns a safe base filename template.
    If 'Title [id].ext' is currently locked, it auto-versions to 'Title [id] (1)', '(2)', etc.
    """
    clean_title = yt_dlp.utils.sanitize_filename(title, restricted=False).strip(". ")
    if not clean_title:
        clean_title = "media"

    base_candidate = f"{clean_title} [{video_id}]" if video_id else clean_title

    def is_candidate_locked(c: str) -> bool:
        for ext in extensions:
            target_path = os.path.join(output_dir, f"{c}.{ext.lstrip('.')}")
            if is_file_locked(target_path):
                return True
        return False

    if not is_candidate_locked(base_candidate):
        return base_candidate

    counter = 1
    while is_candidate_locked(f"{base_candidate} ({counter})"):
        counter += 1
    return f"{base_candidate} ({counter})"


def get_js_runtime_config() -> Optional[Dict[str, Any]]:
    """Locates system Node.js or Deno runtime for yt-dlp JavaScript extraction."""
    node_bin = shutil.which("node")
    if node_bin:
        return {"node": {"path": node_bin}}
    deno_bin = shutil.which("deno")
    if deno_bin:
        return {"deno": {"path": deno_bin}}
    return None


class MediaDownloader:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self._cancel_flag = False
        self._current_ydl = None

    def cancel(self):
        """Signals the current download to abort."""
        self._cancel_flag = True

    def _progress_hook(self, d: Dict[str, Any], callback: Optional[Callable[[Dict[str, Any]], None]]):
        if self._cancel_flag:
            raise DownloadCancelledException("Download cancelled by user.")

        if not callback:
            return

        status = d.get("status")
        if status == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded_bytes = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            percent = 0.0
            if total_bytes > 0:
                percent = (downloaded_bytes / total_bytes) * 100.0
            else:
                p_str = d.get("_percent_str", "0%").replace("%", "").strip()
                try:
                    p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str)
                    percent = float(p_str)
                except ValueError:
                    percent = 0.0

            speed_str = self._format_speed(speed)
            eta_str = self._format_eta(eta)
            size_str = (
                f"{self._format_bytes(downloaded_bytes)} / {self._format_bytes(total_bytes)}"
                if total_bytes
                else self._format_bytes(downloaded_bytes)
            )

            filename = os.path.basename(d.get("filename", "media"))

            callback({
                "status": "downloading",
                "percent": min(max(percent, 0.0), 100.0),
                "speed": speed_str,
                "eta": eta_str,
                "size": size_str,
                "filename": filename,
            })
        elif status == "finished":
            callback({
                "status": "finished",
                "percent": 100.0,
                "speed": "Processing...",
                "eta": "00:00",
                "size": "Done",
                "filename": os.path.basename(d.get("filename", "media")),
            })

    @staticmethod
    def _format_bytes(b: int) -> str:
        if not b:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024.0:
                return f"{b:.1f} {unit}"
            b /= 1024.0
        return f"{b:.1f} PB"

    @staticmethod
    def _format_speed(speed: Optional[float]) -> str:
        if not speed:
            return "-- MB/s"
        return f"{MediaDownloader._format_bytes(int(speed))}/s"

    @staticmethod
    def _format_eta(eta: Optional[int]) -> str:
        if not eta:
            return "--:--"
        mins, secs = divmod(int(eta), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def download(
        self,
        url: str,
        media_type: str = "video",  # "video" or "audio"
        quality: str = "Best Available",
        format_ext: str = "mp4",
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes download with format/quality options and locked-file protection.
        """
        f_lower = (format_ext or "").lower()
        self._cancel_flag = False
        ffmpeg_bin = get_ffmpeg_path()
        js_runtimes = get_js_runtime_config()


        # Step 1: Probe metadata to compute non-conflicting safe filename
        title = "Media"
        video_id = ""
        try:
            probe_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
                "no_warnings": True,
            }
            if js_runtimes:
                probe_opts["js_runtimes"] = js_runtimes
            with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
                info = probe_ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title", "Media")
                    video_id = info.get("id", "")
        except Exception as e:
            logger.warning(f"Metadata probe encountered an issue: {e}")

        # Relevant target extensions for locking check
        if media_type == "audio":
            relevant_exts = ["ac3", "flac", "wav", "mp3", "m4a", "opus", "webm", "ogg"]
        else:
            relevant_exts = [format_ext, "mp4", "mkv", "webm"]

        safe_base = get_safe_base_template(self.output_dir, title, video_id, relevant_exts)
        out_template = os.path.join(self.output_dir, f"{safe_base}.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [lambda d: self._progress_hook(d, progress_callback)],
            "noplaylist": True,
            "writethumbnail": True,
            "windowsfilenames": True,
            "trim_file_name": 160,
            "overwrites": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

        if js_runtimes:
            ydl_opts["js_runtimes"] = js_runtimes

        if ffmpeg_bin:
            ydl_opts["ffmpeg_location"] = ffmpeg_bin

        postprocessors = []
        q_upper = quality.upper()
        f_lower = format_ext.lower()
        is_dolby = ("DOLBY" in q_upper or "UNTOUCHED" in q_upper or f_lower in ["dolby", "ac3"])
        target_dolby_ext = "m4a" if f_lower == "m4a" else "ac3"

        if media_type == "audio":
            ydl_opts["format"] = "bestaudio/best"

            codec = "mp3"
            audio_quality = "320"

            if is_dolby:
                # Handled via dedicated FFmpeg Dolby Digital transcode after stream download
                codec = None
            elif "FLAC" in q_upper or f_lower == "flac":
                codec = "flac"
                audio_quality = "0"
            elif "WAV" in q_upper or f_lower == "wav":
                codec = "wav"
                audio_quality = "0"
            elif "AAC" in q_upper or f_lower in ["m4a", "aac"]:
                codec = "m4a"
                audio_quality = "0"
            elif "OPUS" in q_upper or f_lower == "opus":
                codec = "opus"
                audio_quality = "0"
            else:
                codec = "mp3"
                audio_quality = "320"

            if codec:
                postprocessors.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": audio_quality,
                })
                # For MP3, enforce ID3v2.3 for 100% universal compatibility with Windows Media Player and car stereos
                if codec == "mp3":
                    ydl_opts["postprocessor_args"] = {"FFmpegExtractAudio": ["-id3v2_version", "3"]}

            if add_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_chapters": True})

            if embed_thumbnail and codec in ["mp3", "m4a", "flac"]:
                ydl_opts["writethumbnail"] = True
                postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
                postprocessors.append({"key": "EmbedThumbnail"})

        else:
            # Video Mode
            height_filter = ""
            if "4K" in q_upper or "2160P" in q_upper:
                height_filter = "[height<=2160]"
            elif "2K" in q_upper or "1440P" in q_upper:
                height_filter = "[height<=1440]"
            elif "1080P" in q_upper:
                height_filter = "[height<=1080]"
            elif "720P" in q_upper:
                height_filter = "[height<=720]"
            elif "480P" in q_upper:
                height_filter = "[height<=480]"
            elif "360P" in q_upper:
                height_filter = "[height<=360]"

            ydl_opts["format"] = f"bestvideo{height_filter}+bestaudio/best{height_filter}/bestvideo+bestaudio/best"

            if f_lower in ["mp4", "mkv", "webm"]:
                ydl_opts["merge_output_format"] = f_lower

            if add_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_chapters": True})

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._current_ydl = ydl
                info = ydl.extract_info(url, download=True)
                prepared_name = ydl.prepare_filename(info)

                # Locate actual resulting file
                base, _ = os.path.splitext(prepared_name)
                final_file = prepared_name

                # Dedicated Dolby Digital transcode if requested
                if media_type == "audio" and is_dolby and ffmpeg_bin:
                    raw_audio_candidate = None
                    for cand_ext in [".webm", ".opus", ".m4a", ".ogg", ".mp4", ".mka", ".wav", ".flac"]:
                        c = base + cand_ext
                        if os.path.exists(c):
                            raw_audio_candidate = c
                            break
                    if raw_audio_candidate:
                        dolby_target = base + ("." + target_dolby_ext)
                        acodec = "ac3" if target_dolby_ext == "ac3" else "aac"
                        dolby_cmd = [
                            ffmpeg_bin, "-y", "-i", raw_audio_candidate,
                            "-c:a", acodec,
                            "-b:a", "640k",
                            dolby_target
                        ]
                        try:
                            subprocess.run(dolby_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if os.path.exists(dolby_target) and os.path.getsize(dolby_target) > 0:
                                if raw_audio_candidate != dolby_target:
                                    try:
                                        os.remove(raw_audio_candidate)
                                    except Exception:
                                        pass
                                final_file = dolby_target
                        except Exception as e:
                            logger.error(f"Dolby conversion error: {e}")

                if media_type == "audio":
                    expected_exts = [".ac3", ".flac", ".wav", ".mp3", ".m4a", ".opus", ".webm", ".ogg"]
                    for ext in expected_exts:
                        candidate = base + ext
                        if os.path.exists(candidate):
                            final_file = candidate
                            break
                else:
                    for vext in [f".{f_lower}", ".mp4", ".mkv", ".webm", ".mov"]:
                        cand = base + vext
                        if os.path.exists(cand):
                            final_file = cand
                            break

                # Save thumbnail into .thumbnails folder
                thumb_dir = os.path.join(self.output_dir, ".thumbnails")
                try:
                    os.makedirs(thumb_dir, exist_ok=True)
                    base_name = os.path.basename(base)
                    cached_thumb = os.path.join(thumb_dir, f"{base_name}.jpg")
                    from PIL import Image

                    for thumb_ext in [".webp", ".jpg", ".png", ".jpeg"]:
                        thumb_candidate = base + thumb_ext
                        if os.path.exists(thumb_candidate) and thumb_candidate != final_file:
                            try:
                                if not os.path.exists(cached_thumb):
                                    with Image.open(thumb_candidate) as img:
                                        img.convert("RGB").save(cached_thumb, "JPEG", quality=90)
                                os.remove(thumb_candidate)
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"Thumbnail cache error: {e}")

                return {
                    "success": True,
                    "title": info.get("title", "Media"),
                    "file_path": final_file,
                    "output_dir": self.output_dir,
                }
        except DownloadCancelledException:
            return {"success": False, "cancelled": True, "error": "Download cancelled by user."}
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return {"success": False, "cancelled": False, "error": str(e)}
        finally:
            self._current_ydl = None



