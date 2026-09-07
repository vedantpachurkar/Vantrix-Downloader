import os
import sys
import shutil
import logging

logger = logging.getLogger(__name__)

def get_ffmpeg_path() -> str | None:
    """
    Locates FFmpeg executable on Windows (Windows 10 / 11).
    Priority:
    1. System PATH (e.g. installed via winget or choco on Windows)
    2. Local ./bin folder in application directory
    3. imageio-ffmpeg bundled binary
    """
    # 1. System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # 2. Local bin directory
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_bin = os.path.join(app_dir, "bin")
    binary_name = "ffmpeg.exe"
    local_ffmpeg = os.path.join(local_bin, binary_name)
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg

    # 3. imageio-ffmpeg
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            return bundled
    except Exception as e:
        logger.warning(f"imageio-ffmpeg lookup failed: {e}")

    return None

def verify_ffmpeg() -> dict:
    """
    Returns diagnostics about FFmpeg availability.
    """
    path = get_ffmpeg_path()
    return {
        "available": path is not None and os.path.exists(path),
        "path": path,
        "platform": sys.platform
    }
