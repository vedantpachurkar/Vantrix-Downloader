# ⚡ Vantrix-Downloader — Windows Dedicated Edition

<div align="center">
  <img src="assets/logo.png" alt="Vantrix-Downloader Logo" width="160" style="border-radius: 24px; box-shadow: 0 8px 32px rgba(56, 189, 248, 0.35);" />
  <br/>
  <h3>Next-Generation 4K/HDR Video & Lossless Dolby Audio Media Suite</h3>
  <p>Exclusively designed, tuned, and optimized for <b>Windows 10 and Windows 11</b> with a permanent, ultra-sleek <b>Dark Mode</b>.</p>
</div>

---

## 🌟 Key Features

- **Universal Platform Support**: Paste any video or audio link from **YouTube, Instagram, TikTok, SoundCloud, Bandcamp, Vimeo, Twitter/X, Reddit, Twitch, Facebook, Bilibili**, and over 1,000+ streaming sites.
- **Permanent Pure Dark Mode**:
  - High-contrast neon cyberpunk and deep glassmorphism dark aesthetic (`#06080d`).
  - Eye-strain relief with liquid glass transparency and animated gradient badges.
- **Maximum Video Quality (UHD & HDR)**:
  - **4K Ultra HD** (2160p / 60fps / HDR)
  - **2K Quad HD** (1440p / 60fps)
  - **Full HD** (1080p / 60fps)
  - **HD** (720p) & Standard resolutions (480p, 360p)
  - Preferred Containers: **MP4**, **MKV**, **WebM**
- **Audiophile, Lossless & Dolby Audio Formats (Playable in ANY Player)**:
  - **Dolby Digital AC-3 (`.ac3`)**: Official ATSC A/52 Dolby Digital multi-channel 5.1 surround sound & stereo at 640 kbps. Natively recognized by home theaters, soundbars, AV receivers, VLC, TVs, and media centers.
  - **Dolby Surround M4A (`.m4a`)**: High-bitrate 5.1 surround & stereo audio in an MP4 container, 100% playable out-of-the-box in Windows Media Player, Groove Music, iTunes / Apple Music, and car stereos.
  - **Lossless FLAC (`.flac`)**: Studio Master / 24-bit bit-perfect audio with Vorbis comments and album art (Windows 10/11 native support).
  - **Lossless WAV (`.wav`)**: Uncompressed studio PCM audio (100% universal across all players and DAWs).
  - **MP3 320 kbps (`.mp3`)**: Maximum constant bitrate MP3 with ID3v2.3 tag and embedded cover art, guaranteed to play in 100% of car stereos, Windows Media Player, and mobile devices.
  - **AAC / M4A & OPUS**: High-efficiency modern audiophile codecs with flexible container options (`.m4a`, `.opus`).
- **Bento Download Dashboard**:
  - Real-time download queue with live progress percentage, ETA, and speed metrics.
  - Bento performance tiles displaying active tasks, storage usage, and throughput.
  - Hardware-accelerated local desktop window with glass aesthetic.
- **Downloaded Media Library**:
  - Thumbnail previews for all downloaded videos and lossless audio tracks.
  - Direct disk **Delete** button to safely remove media from your Windows storage.
  - Direct local file opening and browser downloading.
- **Auto-Configured Windows FFmpeg**:
  - Bundled high-performance Windows FFmpeg binary via `imageio-ffmpeg`—no PATH configuration required.

---

## 🚀 How to Run on Windows

Vantrix-Downloader is strictly built for Windows systems.

### Quick Start:
Double-click:
```cmd
run_cinematic_dashboard.bat
```

### Or via Windows PowerShell / Command Prompt:
```powershell
python run_cinematic_dashboard.py
```

Vantrix-Downloader will automatically start the local Windows backend and launch the hardware-accelerated desktop window at `http://127.0.0.1:8080`.

---

## 🧪 Running the Test Suite

Verify all engine and API capabilities on your Windows machine:
```powershell
python tests/test_full_suite.py
```
This validates:
1. Windows FFmpeg binary detection
2. 4K UHD and 24-bit Lossless codec options
3. Local backend server binding (`127.0.0.1`)
4. Link analysis API for 4K video & multi-channel audio
5. Real-time download dispatch and progress polling
6. Media library thumbnail generation and disk file deletion

---

## 📦 Requirements

- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Python**: 3.10, 3.11, 3.12, 3.13, or 3.14
- Dependencies (automatically installed by `run_cinematic_dashboard.bat`):
  - `yt-dlp`
  - `customtkinter`
  - `pillow`
  - `requests`
  - `imageio-ffmpeg`
  - `darkdetect`
  - `pywebview`
  - `bottle`
