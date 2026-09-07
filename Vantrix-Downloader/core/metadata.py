import os
import io
import logging
from typing import Dict, Any, Optional
import requests
from PIL import Image
import yt_dlp

logger = logging.getLogger(__name__)


def format_duration(seconds: Optional[int | float]) -> str:
    if not seconds:
        return "Live / Unknown"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def fetch_metadata(url: str) -> Dict[str, Any]:
    """
    Extracts high-level metadata and available resolutions/audio channels
    without downloading media files. Supports videos and audio streams.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    import shutil
    node_bin = shutil.which("node")
    if node_bin:
        ydl_opts["js_runtimes"] = {"node": {"path": node_bin}}
    elif shutil.which("deno"):
        ydl_opts["js_runtimes"] = {"deno": {"path": shutil.which("deno")}}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Failed to retrieve media information from URL.")

        is_playlist = "entries" in info and bool(info.get("entries"))

        # If it's a playlist, summarize the playlist or first item
        if is_playlist:
            entries = list(info.get("entries") or [])
            title = info.get("title") or "Playlist"
            duration_str = f"{len(entries)} items"
            uploader = info.get("uploader") or info.get("channel") or "Unknown"
            thumbnail_url = entries[0].get("thumbnail") if entries else None
            resolutions = ["Best Quality", "1080p", "720p"]
            max_audio_channels = 2
            return {
                "url": url,
                "title": title,
                "duration": duration_str,
                "uploader": uploader,
                "thumbnail_url": thumbnail_url,
                "is_playlist": True,
                "playlist_count": len(entries),
                "resolutions": resolutions,
                "max_audio_channels": max_audio_channels,
            }

        title = info.get("title", "Unknown Title")
        duration = format_duration(info.get("duration"))
        uploader = info.get("uploader") or info.get("channel") or "Unknown Artist / Uploader"
        thumbnail_url = info.get("thumbnail")

        # Scan formats to determine available resolutions & audio channels
        formats = info.get("formats", [])
        heights = set()
        max_channels = 2

        for f in formats:
            h = f.get("height")
            if h and isinstance(h, int):
                heights.add(h)
            ch = f.get("audio_channels")
            if ch and isinstance(ch, int) and ch > max_channels:
                max_channels = ch

        # Categorize resolutions
        res_list = ["Best Available"]
        if any(h >= 2160 for h in heights):
            res_list.append("4K (2160p)")
        if any(1440 <= h < 2160 for h in heights):
            res_list.append("2K (1440p)")
        if any(1080 <= h < 1440 for h in heights):
            res_list.append("1080p (Full HD)")
        if any(720 <= h < 1080 for h in heights):
            res_list.append("720p (HD)")
        if any(480 <= h < 720 for h in heights):
            res_list.append("480p (SD)")
        if any(h < 480 for h in heights):
            res_list.append("360p")

        return {
            "url": url,
            "title": title,
            "duration": duration,
            "uploader": uploader,
            "thumbnail_url": thumbnail_url,
            "is_playlist": False,
            "playlist_count": 1,
            "resolutions": res_list,
            "max_audio_channels": max_channels,
            "raw_info": info
        }


def fetch_thumbnail_image(thumbnail_url: str, size: tuple = (200, 112)) -> Optional[Image.Image]:
    """
    Downloads and resizes thumbnail to PIL Image.
    """
    if not thumbnail_url:
        return None
    try:
        resp = requests.get(thumbnail_url, timeout=8)
        if resp.status_code == 200:
            img = Image.open(io.BytesIO(resp.content))
            img.thumbnail(size, Image.Resampling.LANCZOS)
            return img
    except Exception as e:
        logger.warning(f"Failed to fetch thumbnail: {e}")
    return None
