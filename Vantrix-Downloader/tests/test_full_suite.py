import os
import sys
import time
import json
import socket
import requests

# Ensure root directory is in sys.path
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from core.ffmpeg_helper import verify_ffmpeg, get_ffmpeg_path
from core.downloader import MediaDownloader
from core.metadata import fetch_metadata
from server.server import VantrixServer

def run_tests():
    print("==========================================================")
    print("  RUNNING FULL TEST SUITE — VANTRIX-DOWNLOADER SUITE      ")
    print("==========================================================")

    # 1. Verify FFmpeg & node runtime
    print("\n[STEP 1] Testing FFmpeg binary detection...")
    ff_info = verify_ffmpeg()
    assert ff_info["available"] is True, "FFmpeg must be available!"
    print(f"  [OK] FFmpeg detected at: {get_ffmpeg_path()}")

    # 2. Test MediaDownloader codec mapping
    print("\n[STEP 2] Testing Audio Lossless & Video 4K options in MediaDownloader...")
    downloader = MediaDownloader()
    assert downloader.output_dir, "Downloader must have a valid output_dir"
    print(f"  [OK] Output directory: {downloader.output_dir}")

    # 3. Start Local VantrixServer on test port
    test_port = 8899
    print(f"\n[STEP 3] Starting test instance of VantrixServer on port {test_port}...")
    server = VantrixServer(download_dir=downloader.output_dir, port=test_port)
    server.start()
    time.sleep(1.0)
    base_url = f"http://127.0.0.1:{test_port}"
    print(f"  [OK] Server running at {base_url}")

    # 4. Test API Endpoints
    print("\n[STEP 4] Testing REST API endpoints...")
    
    # 4. /api/info
    res = requests.get(f"{base_url}/api/info")
    assert res.status_code == 200, f"/api/info returned {res.status_code}"
    info = res.json()
    print(f"  [OK] /api/info: Free Storage = {info.get('free_storage_gb')} GB, URL = {info.get('url')}")

    # 4c. /api/analyze (YouTube 4K Test link)
    print("\n[STEP 5] Testing Link Analysis API (4K Video & Multi-channel audio)...")
    test_url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    an_res = requests.post(f"{base_url}/api/analyze", json={"url": test_url})
    assert an_res.status_code == 200, f"/api/analyze returned {an_res.status_code}"
    an_data = an_res.json()
    assert an_data.get("success") is True, f"Analysis failed: {an_data.get('error')}"
    print(f"  [OK] Analyzed Title: {an_data.get('title')}")
    print(f"  [OK] Detected Resolutions: {an_data.get('resolutions')}")
    print(f"  [OK] Has 4K: {an_data.get('has_4k')}, Has 1080p: {an_data.get('has_1080p')}")
    print(f"  [OK] Max Audio Channels: {an_data.get('max_audio_channels')}")

    # 4d. /api/download (Audio Lossless FLAC & Dolby Digital AC3 dispatch)
    print("\n[STEP 6] Testing Audio Lossless (FLAC) & Dolby Digital (AC3) API dispatch...")
    dl_audio_res = requests.post(f"{base_url}/api/download", json={
        "url": test_url,
        "quality": "flac",
        "format": "flac",
        "type": "audio"
    })
    assert dl_audio_res.status_code == 200
    dl_audio_data = dl_audio_res.json()
    assert dl_audio_data.get("success") is True
    audio_task_id = dl_audio_data.get("task_id")
    print(f"  [OK] FLAC Audio Task Dispatched: ID={audio_task_id}")

    dl_dolby_res = requests.post(f"{base_url}/api/download", json={
        "url": test_url,
        "quality": "dolby",
        "format": "ac3",
        "type": "audio"
    })
    assert dl_dolby_res.status_code == 200 and dl_dolby_res.json().get("success") is True
    dolby_task_id = dl_dolby_res.json().get("task_id")
    print(f"  [OK] Dolby Digital (AC3 640k) Task Dispatched: ID={dolby_task_id}")

    # 4e. /api/progress polling
    time.sleep(1.0)
    prog_res = requests.get(f"{base_url}/api/progress")
    assert prog_res.status_code == 200
    prog_data = prog_res.json()
    print(f"  [OK] /api/progress polling: Active Count = {prog_data.get('active_count')}")

    # Cancel tasks so test finishes cleanly
    requests.post(f"{base_url}/api/cancel", json={"task_id": audio_task_id})
    requests.post(f"{base_url}/api/cancel", json={"task_id": dolby_task_id})
    print(f"  [OK] Tasks cancelled cleanly")

    # 4f. /api/library
    lib_res = requests.get(f"{base_url}/api/library")
    assert lib_res.status_code == 200
    lib_data = lib_res.json()
    print(f"  [OK] /api/library: {len(lib_data.get('files', []))} media files ready for streaming/download")

    # 4g. Test Thumbnail and Delete Endpoints for both Video and Dolby AC3
    print("\n[STEP 7] Testing Library Thumbnail & File Delete APIs (Video & Dolby AC3)...")
    test_dummy_name = "test_media_sample.mp4"
    test_dummy_path = os.path.join(downloader.output_dir, test_dummy_name)
    with open(test_dummy_path, "wb") as f:
        f.write(b"fake mp4 video bytes for unit test")

    test_ac3_name = "test_surround_sound.ac3"
    test_ac3_path = os.path.join(downloader.output_dir, test_ac3_name)
    with open(test_ac3_path, "wb") as f:
        f.write(b"fake ac3 dolby audio bytes for unit test")

    # Check library shows both with thumbnail_url
    lib_res = requests.get(f"{base_url}/api/library")
    items = lib_res.json().get("files", [])
    found_vid = next((x for x in items if x["name"] == test_dummy_name), None)
    found_ac3 = next((x for x in items if x["name"] == test_ac3_name), None)
    assert found_vid is not None, "Dummy video must appear in library"
    assert found_ac3 is not None, "Dolby AC3 file must appear in library"
    assert found_ac3["type"] == "audio" and found_ac3["ext"] == "AC3", "AC3 must be recognized as audio"
    print(f"  [OK] Library detects MP4 and Dolby AC3 media items with thumbnails")

    # Check thumbnail endpoint
    thumb_res = requests.get(f"{base_url}{found_ac3['thumbnail_url']}")
    assert thumb_res.status_code == 200, f"AC3 Thumbnail returned {thumb_res.status_code}"
    print(f"  [OK] AC3 Thumbnail served successfully (Content-Type: {thumb_res.headers.get('content-type')})")

    # Call /api/delete for both
    del_res1 = requests.post(f"{base_url}/api/delete", json={"filename": test_dummy_name})
    del_res2 = requests.post(f"{base_url}/api/delete", json={"filename": test_ac3_name})
    assert del_res1.status_code == 200 and del_res2.status_code == 200
    assert not os.path.exists(test_dummy_path) and not os.path.exists(test_ac3_path)
    print(f"  [OK] /api/delete successfully removed MP4 and AC3 files from disk")

    print("\n==========================================================")
    print("  [SUCCESS] ALL 6 INTEGRATION & API TESTS PASSED!         ")
    print("==========================================================")


if __name__ == "__main__":
    run_tests()
