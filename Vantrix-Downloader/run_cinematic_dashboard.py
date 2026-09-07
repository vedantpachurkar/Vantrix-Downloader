"""
Vantrix-Downloader — Windows Dedicated Edition
Exclusively designed and optimized for Windows 10 and Windows 11.
"""

import os
import sys
import time
import platform
import webbrowser

import ctypes

# Strict Windows OS check
if sys.platform != "win32":
    print("\n[ERROR] Vantrix-Downloader is designed exclusively for Windows (Windows 10 / 11).")
    print(f"Current detected operating system: {sys.platform}")
    print("Vantrix-Downloader does not support macOS, Linux, iOS, or Android.")
    sys.exit(1)

# Explicit Windows AppUserModelID ensures taskbar groups separately from python.exe
try:
    myappid = "vantrix.downloader.windows.dedicated.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# Ensure UTF-8 console output for banners on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from server.server import VantrixServer


def set_windows_taskbar_icon(hwnd: int, ico_path: str):
    """Explicitly assigns 32x32 (Taskbar) and 16x16 (Titlebar) icons using Win32 API."""
    if not hwnd or not os.path.exists(ico_path):
        return
    try:
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010

        # Load 32x32 for Taskbar, Alt+Tab, and Task Manager
        h_icon_big = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if h_icon_big:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)

        # Load 16x16 for Window Titlebar and System Menu
        h_icon_small = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if h_icon_small:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)
    except Exception:
        pass


def print_banner(local_url: str, download_dir: str):
    banner = f"""
======================================================================
  ⚡ VANTRIX-DOWNLOADER — DEDICATED WINDOWS MEDIA SUITE (WIN 10 / 11)
  4K Ultra HD Video (2160p) & Lossless Studio / Dolby Audio
======================================================================

  💻 Local Dashboard URL:
     → {local_url}

  📁 Windows Downloads Directory:
     → {download_dir}

  Hardware: Hardware-accelerated liquid-glass window running locally.
======================================================================
"""
    print(banner)


def main():
    # Base Windows download folder
    download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    port = 8080
    local_url = f"http://127.0.0.1:{port}"
    ico_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "logo.ico"))

    # Apply taskbar icon to console window if running via command prompt / batch
    try:
        console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if console_hwnd:
            set_windows_taskbar_icon(console_hwnd, ico_path)
    except Exception:
        pass

    # Start local server bound to 127.0.0.1 for local Windows usage
    server = VantrixServer(download_dir=download_dir, port=port, host="127.0.0.1")
    server.start()

    time.sleep(0.4)
    print_banner(local_url, download_dir)
    print("[READY] Vantrix-Downloader Windows engine is running! Press Ctrl+C to stop.\n")

    # Launch native hardware-accelerated desktop window
    launched_webview = False
    try:
        import webview
        window = webview.create_window(
            title="Vantrix-Downloader — Windows Dedicated Edition",
            url=local_url,
            width=1280,
            height=840,
            min_size=(920, 600),
            background_color="#06080d"
        )

        def on_shown():
            try:
                hwnd = None
                if hasattr(window, "native") and window.native:
                    hwnd = int(window.native.Handle.ToInt64())
                elif hasattr(window, "gui") and hasattr(window.gui, "Handle"):
                    hwnd = int(window.gui.Handle.ToInt64())
                if hwnd:
                    set_windows_taskbar_icon(hwnd, ico_path)
            except Exception:
                pass

        window.events.shown += on_shown
        launched_webview = True
        webview.start(icon=ico_path)
    except Exception as e:
        print(f"[NOTE] Webview window unavailable ({e}). Opening Windows default browser...")
        try:
            webbrowser.open(local_url)
        except Exception:
            pass

    # If webview closed or ran in browser, keep process alive until Ctrl+C
    if not launched_webview:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Vantrix-Downloader...")


if __name__ == "__main__":
    main()
