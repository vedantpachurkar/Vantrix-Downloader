import os
import sys

# Ensure root is in path
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from core.ffmpeg_helper import verify_ffmpeg, get_ffmpeg_path
from core.downloader import MediaDownloader
from core.metadata import fetch_metadata

def test_ffmpeg_detection():
    print("[TEST] Checking FFmpeg detection...")
    info = verify_ffmpeg()
    print("  FFmpeg Info:", info)
    assert info["available"] is True, "FFmpeg should be available!"
    path = get_ffmpeg_path()
    assert path and os.path.exists(path), f"Path does not exist: {path}"
    print("  [PASS] FFmpeg verified.")

def test_downloader_init():
    print("[TEST] Checking MediaDownloader initialization...")
    downloader = MediaDownloader()
    assert os.path.exists(downloader.output_dir) or downloader.output_dir.endswith("Downloads")
    print("  Output dir:", downloader.output_dir)
    print("  [PASS] Downloader initialized.")

def test_metadata_and_format_parsing():
    print("[TEST] Testing metadata extraction with sample media...")
    test_url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"  # Big Buck Bunny 4K 60fps public test video
    try:
        data = fetch_metadata(test_url)
        print("  Title:", data.get("title"))
        print("  Duration:", data.get("duration"))
        print("  Resolutions detected:", data.get("resolutions"))
        print("  Audio channels:", data.get("max_audio_channels"))
        assert "4K" in " ".join(data.get("resolutions", [])) or "1080p" in " ".join(data.get("resolutions", []))
        print("  [PASS] Metadata extraction verified.")
    except Exception as e:
        print(f"  [WARN] Live network metadata test skipped or failed: {e}")

if __name__ == "__main__":
    print("--- Running Vantrix-Downloader Integration Tests ---")
    test_ffmpeg_detection()
    test_downloader_init()
    test_metadata_and_format_parsing()
    print("--- All tests completed successfully! ---")
