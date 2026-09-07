import os
import sys

# Strict Windows OS check
if sys.platform != "win32":
    print("\n[ERROR] Vantrix-Downloader is designed exclusively for Windows (Windows 10 / 11).")
    print(f"Current detected operating system: {sys.platform}")
    print("Vantrix-Downloader does not support macOS, Linux, iOS, or Android.")
    sys.exit(1)

import threading
import subprocess
import webbrowser
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

from core.ffmpeg_helper import verify_ffmpeg
from core.metadata import fetch_metadata, fetch_thumbnail_image
from core.downloader import MediaDownloader
from player.universal_player import play_in_background
from server.server import VantrixServer

# Set modern theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class VantrixDownloaderApp(ctk.CTk):
    def __init__(self):
        # Set Windows explicit AppUserModelID so taskbar displays app icon instead of python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("vantrix.downloader.windows.dedicated.1.0")
        except Exception:
            pass

        super().__init__()

        self.title("Vantrix-Downloader — Windows Dedicated Edition (4K Video & Lossless Audio)")
        
        # Set taskbar and window icon
        ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass
        
        # Responsive sizing
        self.geometry("940x640")
        self.minsize(800, 540)

        # Default download folder
        self.download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.downloader = MediaDownloader(output_dir=self.download_dir)
        self.current_metadata = None
        self.is_downloading = False
        self.last_downloaded_file = None

        # Start Local Media Server in background for Windows browser dashboard access
        self.media_server = VantrixServer(download_dir=self.download_dir, port=8080)
        self.media_server.start()
        self.mobile_server = self.media_server

        # Build Main Scrollable Canvas
        self._build_layout()

        # Check FFmpeg in background
        self._check_system_status()

    def _build_layout(self):
        # Header (Fixed at top)
        self._create_header()

        # Main Scrollable Container
        self.scroll_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_container.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # 1. URL Input & Action Row
        self._create_url_section()

        # 2. Format & Quality Options
        self._create_format_options_section()

        # 3. Media Preview Card
        self._create_preview_section()

        # 4. Download & Progress Dashboard (with Built-in Player action!)
        self._create_progress_section()

        # 5. Destination Folder & Settings
        self._create_settings_section()

    def _create_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(12, 6))

        # Title & Subtitle
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left")

        title_label = ctk.CTkLabel(
            title_box,
            text="⚡ Vantrix-Downloader",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=("#1f538d", "#38bdf8")
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            title_box,
            text="Dedicated 4K/HDR Video & Lossless Audio Downloader • Windows 10 & 11",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        subtitle_label.pack(anchor="w")

        # Action Buttons on right
        right_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_box.pack(side="right")

        # Standalone Player button
        player_btn = ctk.CTkButton(
            right_box,
            text="▶️ Open Player",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#8b5cf6", "#6d28d9"),
            hover_color=("#7c3aed", "#5b21b6"),
            height=32,
            command=self._open_player_file_dialog
        )
        player_btn.pack(side="right", padx=5)

        # Engine Badge
        self.ffmpeg_badge = ctk.CTkLabel(
            right_box,
            text="Checking Engine...",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#e0e0e0", "#1e293b"),
            corner_radius=8,
            padx=10,
            pady=4
        )
        self.ffmpeg_badge.pack(side="right", padx=5)

    def _check_system_status(self):
        def check():
            info = verify_ffmpeg()
            if info.get("available"):
                self.after(0, lambda: self.ffmpeg_badge.configure(
                    text="✓ 4K & Lossless Ready",
                    text_color="#10b981",
                    fg_color=("#d1fae5", "#064e3b")
                ))
            else:
                self.after(0, lambda: self.ffmpeg_badge.configure(
                    text="⚠ FFmpeg Missing",
                    text_color="#ef4444",
                    fg_color=("#fee2e2", "#7f1d1d")
                ))
        threading.Thread(target=check, daemon=True).start()

    def _create_url_section(self):
        card = ctk.CTkFrame(self.scroll_container, corner_radius=10)
        card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            inner,
            text="Paste Video or Audio Link:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 6))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            row,
            placeholder_text="Paste any YouTube, Vimeo, TikTok, SoundCloud, Instagram, Twitter/X, Reddit link here...",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self._on_url_submitted())

        paste_btn = ctk.CTkButton(
            row,
            text="📋 Paste",
            width=75,
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._paste_clipboard
        )
        paste_btn.pack(side="left", padx=(0, 8))

        self.inspect_btn = ctk.CTkButton(
            row,
            text="🔍 Inspect",
            width=90,
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#3b82f6", "#2563eb"),
            hover_color=("#2563eb", "#1d4ed8"),
            command=self._start_inspect_link
        )
        self.inspect_btn.pack(side="left")

    def _paste_clipboard(self):
        try:
            text = self.clipboard_get().strip()
            if text:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, text)
                self._start_inspect_link()
        except Exception:
            pass

    def _on_url_submitted(self):
        self._start_inspect_link()

    def _create_format_options_section(self):
        self.options_card = ctk.CTkFrame(self.scroll_container, corner_radius=10)
        self.options_card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(self.options_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Header Row: Mode Switcher Tabs
        row_mode = ctk.CTkFrame(inner, fg_color="transparent")
        row_mode.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            row_mode,
            text="Choose Media Format:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left", padx=(0, 15))

        self.mode_var = ctk.StringVar(value="video")
        self.mode_segmented = ctk.CTkSegmentedButton(
            row_mode,
            values=["🎬 Video + Audio (4K / 1080p / 720p)", "🎵 Audio Only (Lossless / Dolby / MP3)"],
            command=self._on_mode_switched,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32
        )
        self.mode_segmented.set("🎬 Video + Audio (4K / 1080p / 720p)")
        self.mode_segmented.pack(side="left")

        # Quality & Container Controls
        self.controls_row = ctk.CTkFrame(inner, fg_color="transparent")
        self.controls_row.pack(fill="x", pady=(2, 4))

        # Quality Dropdown
        self.quality_label = ctk.CTkLabel(
            self.controls_row,
            text="Quality:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.quality_label.pack(side="left", padx=(0, 6))

        self.video_qualities = [
            "🌟 Best Available (Max 4K / 8K HDR)",
            "🎬 4K Ultra HD (2160p)",
            "🖥️ 2K Quad HD (1440p)",
            "✨ 1080p Full HD (60fps)",
            "📺 720p HD",
            "📱 480p / 360p Standard"
        ]

        self.audio_qualities = [
            "💎 Lossless FLAC (Studio Quality / 24-bit)",
            "🎼 Lossless WAV (Uncompressed PCM)",
            "🔊 Dolby Digital AC3 (5.1 Surround / 640k)",
            "🎧 MP3 (320 kbps Maximum Bitrate)",
            "⚡ AAC / M4A (High Bitrate)",
            "🌐 OPUS (Audiophile Standard)"
        ]

        self.quality_dropdown = ctk.CTkOptionMenu(
            self.controls_row,
            values=self.video_qualities,
            width=300,
            height=32,
            font=ctk.CTkFont(size=12)
        )
        self.quality_dropdown.pack(side="left", padx=(0, 15))

        # Container / Extension Dropdown
        self.format_label = ctk.CTkLabel(
            self.controls_row,
            text="Container:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.format_label.pack(side="left", padx=(0, 6))

        self.video_formats = ["mp4", "mkv", "webm"]
        self.audio_formats = ["ac3", "m4a", "mp3", "flac", "wav", "opus"]

        self.format_dropdown = ctk.CTkOptionMenu(
            self.controls_row,
            values=self.video_formats,
            width=90,
            height=32,
            font=ctk.CTkFont(size=12)
        )
        self.format_dropdown.pack(side="left", padx=(0, 15))

        # Checkbox
        self.embed_tags_chk = ctk.CTkCheckBox(
            self.controls_row,
            text="Embed Album Art & ID3 Tags",
            font=ctk.CTkFont(size=12)
        )
        self.embed_tags_chk.select()
        self.embed_tags_chk.pack(side="left")

    def _on_mode_switched(self, value):
        if "Video" in value:
            self.mode_var.set("video")
            self.quality_dropdown.configure(values=self.video_qualities)
            self.quality_dropdown.set(self.video_qualities[0])
            self.format_dropdown.configure(values=self.video_formats)
            self.format_dropdown.set("mp4")
        else:
            self.mode_var.set("audio")
            self.quality_dropdown.configure(values=self.audio_qualities)
            self.quality_dropdown.set(self.audio_qualities[0])
            self.format_dropdown.configure(values=self.audio_formats)
            self.format_dropdown.set("flac")

    def _create_preview_section(self):
        self.preview_card = ctk.CTkFrame(self.scroll_container, corner_radius=10)
        self.preview_card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        # Left: Thumbnail placeholder
        self.thumb_label = ctk.CTkLabel(
            inner,
            text="[ Thumbnail ]",
            width=150,
            height=85,
            fg_color=("#e2e8f0", "#1e293b"),
            corner_radius=8
        )
        self.thumb_label.pack(side="left", padx=(0, 12))

        # Right: Info details
        info_box = ctk.CTkFrame(inner, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True)

        self.meta_title = ctk.CTkLabel(
            info_box,
            text="Paste a link above to preview info & stream qualities",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            wraplength=550,
            justify="left"
        )
        self.meta_title.pack(anchor="w", pady=(0, 3))

        self.meta_subtitle = ctk.CTkLabel(
            info_box,
            text="Ready • Works with YouTube, TikTok, SoundCloud, Instagram, Twitter/X, Vimeo...",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.meta_subtitle.pack(anchor="w", pady=(0, 4))

        # Badges row
        self.badges_row = ctk.CTkFrame(info_box, fg_color="transparent")
        self.badges_row.pack(anchor="w")

        self.audio_badge = ctk.CTkLabel(
            self.badges_row,
            text="🎧 Audio: High Fidelity",
            font=ctk.CTkFont(size=11),
            fg_color=("#e2e8f0", "#1e293b"),
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.audio_badge.pack(side="left", padx=(0, 6))

        self.video_badge = ctk.CTkLabel(
            self.badges_row,
            text="🎬 Video: Up to 4K",
            font=ctk.CTkFont(size=11),
            fg_color=("#e2e8f0", "#1e293b"),
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.video_badge.pack(side="left")

    def _create_progress_section(self):
        self.action_card = ctk.CTkFrame(self.scroll_container, corner_radius=10, fg_color=("#f1f5f9", "#0f172a"))
        self.action_card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(self.action_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Big Action Buttons Row
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 8))

        self.download_btn = ctk.CTkButton(
            btn_row,
            text="⬇️ START DOWNLOAD NOW",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._start_download
        )
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.cancel_btn = ctk.CTkButton(
            btn_row,
            text="⏹️ Cancel",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=44,
            width=80,
            fg_color="#ef4444",
            hover_color="#dc2626",
            state="disabled",
            command=self._cancel_download
        )
        self.cancel_btn.pack(side="left", padx=(0, 8))

        # Built-in Universal Player button!
        self.play_btn = ctk.CTkButton(
            btn_row,
            text="▶️ Play Media",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=44,
            width=110,
            fg_color=("#8b5cf6", "#7c3aed"),
            hover_color=("#7c3aed", "#6d28d9"),
            state="disabled",
            command=self._play_last_downloaded
        )
        self.play_btn.pack(side="left", padx=(0, 8))

        self.open_folder_btn = ctk.CTkButton(
            btn_row,
            text="📂 Open Folder",
            font=ctk.CTkFont(size=12),
            height=44,
            width=100,
            command=self._open_download_folder
        )
        self.open_folder_btn.pack(side="left")

        # Status & Stats Row
        stats_box = ctk.CTkFrame(inner, fg_color="transparent")
        stats_box.pack(fill="x", pady=(2, 4))

        self.status_label = ctk.CTkLabel(
            stats_box,
            text="Status: Ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.status_label.pack(side="left")

        self.stats_label = ctk.CTkLabel(
            stats_box,
            text="Speed: -- | ETA: -- | Size: --",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="e"
        )
        self.stats_label.pack(side="right")

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(inner, height=12)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", pady=(2, 0))

    def _create_settings_section(self):
        card = ctk.CTkFrame(self.scroll_container, corner_radius=10)
        card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")

        ctk.CTkLabel(
            row,
            text="Download Location:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 8))

        self.path_entry = ctk.CTkEntry(row, height=32, font=ctk.CTkFont(size=11))
        self.path_entry.insert(0, self.download_dir)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            row,
            text="📁 Change...",
            width=80,
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._browse_folder
        )
        browse_btn.pack(side="left")

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.downloader.output_dir = folder
            self.mobile_server.download_dir = folder

    def _start_inspect_link(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Required", "Please paste or enter a media link first.")
            return

        self.inspect_btn.configure(state="disabled", text="Checking...")
        self.meta_title.configure(text="Fetching stream data from link...")
        self.status_label.configure(text="Status: Contacting server...")

        def worker():
            try:
                meta = fetch_metadata(url)
                thumb_img = fetch_thumbnail_image(meta.get("thumbnail_url"))
                self.after(0, lambda: self._apply_metadata(meta, thumb_img))
            except Exception as e:
                self.after(0, lambda: self._apply_metadata_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_metadata(self, meta: dict, thumb_img: Optional[Image.Image]):
        self.inspect_btn.configure(state="normal", text="🔍 Inspect")
        self.current_metadata = meta

        self.meta_title.configure(text=meta.get("title", "Unknown Title"))
        uploader = meta.get("uploader", "Unknown")
        duration = meta.get("duration", "Unknown")
        self.meta_subtitle.configure(text=f"By: {uploader} | Duration: {duration}")

        channels = meta.get("max_audio_channels", 2)
        if channels >= 6:
            self.audio_badge.configure(
                text=f"🔊 Dolby 5.1 Surround ({channels}ch)",
                fg_color=("#dbeafe", "#1e3a8a"),
                text_color=("#1d4ed8", "#93c5fd")
            )
        else:
            self.audio_badge.configure(
                text="🎧 Lossless/Stereo Ready",
                fg_color=("#d1fae5", "#064e3b"),
                text_color=("#047857", "#6ee7b7")
            )

        resolutions = meta.get("resolutions", [])
        if "4K (2160p)" in resolutions:
            self.video_badge.configure(
                text="🌟 4K Ultra HD Stream",
                fg_color=("#fef3c7", "#78350f"),
                text_color=("#b45309", "#fcd34d")
            )
        elif "1080p (Full HD)" in resolutions:
            self.video_badge.configure(
                text="✨ 1080p Full HD",
                fg_color=("#e0f2fe", "#075985"),
                text_color=("#0369a1", "#7dd3fc")
            )
        else:
            self.video_badge.configure(
                text="📺 Best Available Video",
                fg_color=("#e2e8f0", "#1e293b"),
                text_color=("#334155", "#cbd5e1")
            )

        if thumb_img:
            photo = ctk.CTkImage(light_image=thumb_img, dark_image=thumb_img, size=thumb_img.size)
            self.thumb_label.configure(image=photo, text="")
            self.thumb_label.image = photo

        self.status_label.configure(text="Status: Link ready. Click Download Now!")

    def _apply_metadata_error(self, err_msg: str):
        self.inspect_btn.configure(state="normal", text="🔍 Inspect")
        self.meta_title.configure(text="Ready to download")
        self.status_label.configure(text="Status: Ready (Direct download enabled)")

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Required", "Please paste or enter a media link first.")
            return

        if self.is_downloading:
            return

        custom_folder = self.path_entry.get().strip()
        if custom_folder:
            try:
                os.makedirs(custom_folder, exist_ok=True)
                self.download_dir = custom_folder
                self.downloader.output_dir = custom_folder
                self.mobile_server.download_dir = custom_folder
            except Exception:
                pass

        media_type = self.mode_var.get()
        quality = self.quality_dropdown.get()
        format_ext = self.format_dropdown.get()
        embed_meta = bool(self.embed_tags_chk.get())

        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="⏳ DOWNLOADING...")
        self.cancel_btn.configure(state="normal")
        self.play_btn.configure(state="disabled")
        self.progress_bar.set(0.0)
        self.status_label.configure(text=f"Status: Connecting & downloading ({quality})...")

        def progress_callback(data: dict):
            status = data.get("status")
            if status == "downloading":
                pct = data.get("percent", 0.0) / 100.0
                speed = data.get("speed", "-- MB/s")
                eta = data.get("eta", "--:--")
                size = data.get("size", "")
                fname = data.get("filename", "")
                self.after(0, lambda: self._update_progress_ui(pct, speed, eta, size, fname))
            elif status == "finished":
                self.after(0, lambda: self._finish_progress_ui())

        def worker():
            res = self.downloader.download(
                url=url,
                media_type=media_type,
                quality=quality,
                format_ext=format_ext,
                embed_thumbnail=embed_meta,
                add_metadata=embed_meta,
                progress_callback=progress_callback
            )
            self.after(0, lambda: self._download_complete(res))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress_ui(self, pct: float, speed: str, eta: str, size: str, filename: str):
        self.progress_bar.set(pct)
        pct_display = int(pct * 100)
        self.status_label.configure(text=f"Status: Downloading ({pct_display}%) | {filename[:30]}")
        self.stats_label.configure(text=f"Speed: {speed} | ETA: {eta} | Size: {size}")

    def _finish_progress_ui(self):
        self.progress_bar.set(1.0)
        self.status_label.configure(text="Status: Merging streams with FFmpeg...")
        self.stats_label.configure(text="Processing final file...")

    def _download_complete(self, res: dict):
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="⬇️ START DOWNLOAD NOW")
        self.cancel_btn.configure(state="disabled")

        if res.get("cancelled"):
            self.status_label.configure(text="Status: Download was cancelled.")
            self.stats_label.configure(text="Cancelled")
            self.progress_bar.set(0.0)
            messagebox.showinfo("Cancelled", "The download was cancelled.")
        elif res.get("success"):
            file_path = res.get("file_path", "")
            self.last_downloaded_file = file_path
            self.play_btn.configure(state="normal")
            self.status_label.configure(text="Status: ✓ Completed & Ready to Play!")
            self.stats_label.configure(text="Saved successfully")
            self.progress_bar.set(1.0)
            
            # Show completion prompt with option to play immediately
            ans = messagebox.askyesno(
                "Download Successful! 🎉",
                f"Media saved successfully!\n\nFile: {os.path.basename(file_path)}\n\nWould you like to play it now in the built-in player?"
            )
            if ans:
                self._play_last_downloaded()
        else:
            err = res.get("error", "Unknown error occurred.")
            self.status_label.configure(text="Status: Download failed.")
            self.stats_label.configure(text="Error")
            messagebox.showerror("Download Error", f"Download encountered an issue:\n\n{err}")

    def _cancel_download(self):
        if self.is_downloading:
            self.downloader.cancel()
            self.status_label.configure(text="Status: Cancelling...")

    def _play_last_downloaded(self):
        if self.last_downloaded_file and os.path.exists(self.last_downloaded_file):
            play_in_background(self.last_downloaded_file)

    def _open_player_file_dialog(self):
        file_path = filedialog.askopenfilename(
            initialdir=self.download_dir,
            title="Select Any Video or Audio to Play",
            filetypes=[
                ("All Media Files", "*.mp4 *.mkv *.webm *.flac *.wav *.mp3 *.m4a *.opus *.avi *.mov *.ogg"),
                ("Video Files", "*.mp4 *.mkv *.webm *.avi *.mov"),
                ("Audio Files", "*.flac *.wav *.mp3 *.m4a *.opus *.ogg"),
                ("All Files", "*.*")
            ]
        )
        if file_path:
            play_in_background(file_path)

    def _open_download_folder(self):
        folder = self.download_dir
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        os.startfile(folder)


def main():
    app = VantrixDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
