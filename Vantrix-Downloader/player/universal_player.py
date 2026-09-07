import os
import sys
import mimetypes
import socket
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote
import webview


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class RangeRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP handler with full Range request support (RFC 7233)
    allowing instant seeking/scrubbing in 4K/1080p video and lossless audio.
    """
    target_file = None

    def log_message(self, format, *args):
        # Silence console logging for media chunks
        pass

    def do_GET(self):
        if not self.target_file or not os.path.exists(self.target_file):
            self.send_error(404, "File Not Found")
            return

        file_size = os.path.getsize(self.target_file)
        mime_type, _ = mimetypes.guess_type(self.target_file)
        if not mime_type:
            ext = os.path.splitext(self.target_file)[1].lower()
            if ext == ".flac":
                mime_type = "audio/flac"
            elif ext == ".mkv":
                mime_type = "video/x-matroska"
            elif ext == ".opus":
                mime_type = "audio/opus"
            else:
                mime_type = "application/octet-stream"

        range_header = self.headers.get("Range")
        if range_header:
            # Parse Range: bytes=START-END
            try:
                range_val = range_header.strip().split("=")[1]
                start_str, end_str = range_val.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                content_length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                with open(self.target_file, "rb") as f:
                    f.seek(start)
                    bytes_remaining = content_length
                    chunk_size = 64 * 1024
                    while bytes_remaining > 0:
                        to_read = min(chunk_size, bytes_remaining)
                        data = f.read(to_read)
                        if not data:
                            break
                        self.wfile.write(data)
                        bytes_remaining -= len(data)
            except Exception:
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            try:
                with open(self.target_file, "rb") as f:
                    shutil_copy(f, self.wfile)
            except Exception:
                pass


def shutil_copy(source, target, length=64 * 1024):
    while True:
        buf = source.read(length)
        if not buf:
            break
        target.write(buf)


def generate_player_html(media_url: str, title: str, is_audio: bool) -> str:
    escaped_title = title.replace('"', '&quot;').replace("<", "&lt;")
    
    if is_audio:
        media_tag = f"""
        <div class="audio-container">
            <div class="vinyl-record">
                <div class="vinyl-art">🎵</div>
            </div>
            <div class="track-title">{escaped_title}</div>
            <div class="visualizer" id="visualizer">
                <div class="bar"></div><div class="bar"></div><div class="bar"></div>
                <div class="bar"></div><div class="bar"></div><div class="bar"></div>
                <div class="bar"></div><div class="bar"></div><div class="bar"></div>
            </div>
            <audio id="player" controls autoplay style="width: 100%; max-width: 600px; margin-top: 20px;">
                <source src="{media_url}">
                Your system does not support HTML5 audio playback.
            </audio>
        </div>
        """
    else:
        media_tag = f"""
        <div class="video-container">
            <video id="player" controls autoplay playsinline style="width: 100%; height: 100%; object-fit: contain;">
                <source src="{media_url}">
                Your system does not support HTML5 video playback.
            </video>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_title} - OmniPlayer</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            background-color: #0b0f19;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            user-select: none;
        }}
        .header-bar {{
            height: 48px;
            background: #111827;
            display: flex;
            align-items: center;
            padding: 0 16px;
            border-bottom: 1px solid #1f2937;
            justify-content: space-between;
        }}
        .header-title {{
            font-size: 14px;
            font-weight: 600;
            color: #e2e8f0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 70%;
        }}
        .badge {{
            font-size: 11px;
            background: #2563eb;
            color: #ffffff;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}
        .player-viewport {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000000;
            position: relative;
        }}
        .video-container {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .audio-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 30px;
        }}
        .vinyl-record {{
            width: 160px;
            height: 160px;
            border-radius: 50%;
            background: radial-gradient(circle, #1e293b 0%, #0f172a 70%, #020617 100%);
            border: 4px solid #334155;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            animation: spin 8s linear infinite;
        }}
        @keyframes spin {{
            100% {{ transform: rotate(360deg); }}
        }}
        .vinyl-art {{
            font-size: 54px;
        }}
        .track-title {{
            margin-top: 24px;
            font-size: 18px;
            font-weight: 700;
            text-align: center;
            color: #f1f5f9;
            max-width: 80%;
        }}
        .visualizer {{
            display: flex;
            align-items: flex-end;
            gap: 6px;
            height: 40px;
            margin-top: 18px;
        }}
        .bar {{
            width: 6px;
            background: #38bdf8;
            border-radius: 3px;
            animation: bounce 1.2s ease-in-out infinite alternate;
        }}
        .bar:nth-child(2) {{ animation-delay: 0.2s; height: 70%; }}
        .bar:nth-child(3) {{ animation-delay: 0.4s; height: 100%; }}
        .bar:nth-child(4) {{ animation-delay: 0.1s; height: 50%; }}
        .bar:nth-child(5) {{ animation-delay: 0.5s; height: 85%; }}
        .bar:nth-child(6) {{ animation-delay: 0.3s; height: 60%; }}
        .bar:nth-child(7) {{ animation-delay: 0.6s; height: 95%; }}
        .bar:nth-child(8) {{ animation-delay: 0.2s; height: 40%; }}
        .bar:nth-child(9) {{ animation-delay: 0.4s; height: 75%; }}
        @keyframes bounce {{
            0% {{ height: 15%; }}
            100% {{ height: 100%; }}
        }}
        .footer-shortcuts {{
            height: 32px;
            background: #0f172a;
            border-top: 1px solid #1e293b;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            color: #94a3b8;
            gap: 16px;
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div class="header-title">⚡ {escaped_title}</div>
        <div class="badge">{"🎵 LOSSLESS AUDIO" if is_audio else "🎬 4K / HD VIDEO"}</div>
    </div>
    <div class="player-viewport">
        {media_tag}
    </div>
    <div class="footer-shortcuts">
        <span><b>Space:</b> Play/Pause</span>
        <span><b>← / →:</b> Seek ±5s</span>
        <span><b>↑ / ↓:</b> Volume ±10%</span>
        <span><b>F:</b> Fullscreen</span>
    </div>
    <script>
        const player = document.getElementById('player');
        window.addEventListener('keydown', (e) => {{
            if (e.code === 'Space') {{
                e.preventDefault();
                player.paused ? player.play() : player.pause();
            }} else if (e.code === 'ArrowRight') {{
                player.currentTime = Math.min(player.duration, player.currentTime + 5);
            }} else if (e.code === 'ArrowLeft') {{
                player.currentTime = Math.max(0, player.currentTime - 5);
            }} else if (e.code === 'ArrowUp') {{
                e.preventDefault();
                player.volume = Math.min(1, player.volume + 0.1);
            }} else if (e.code === 'ArrowDown') {{
                e.preventDefault();
                player.volume = Math.max(0, player.volume - 0.1);
            }} else if (e.code === 'KeyF') {{
                if (!document.fullscreenElement) {{
                    document.documentElement.requestFullscreen().catch(() => {{}});
                }} else {{
                    document.exitFullscreen().catch(() => {{}});
                }}
            }}
        }});
    </script>
</body>
</html>
"""


def start_streaming_server(filepath: str, port: int):
    RangeRequestHandler.target_file = filepath
    server = HTTPServer(("127.0.0.1", port), RangeRequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server


def launch_player_window(filepath: str, title: Optional[str] = None):
    """
    Opens the hardware-accelerated Universal Media Player window.
    """
    if not os.path.exists(filepath):
        print(f"[ERROR] Media file not found: {filepath}")
        return

    port = find_free_port()
    start_streaming_server(filepath, port)

    ext = os.path.splitext(filepath)[1].lower()
    is_audio = ext in [".flac", ".wav", ".mp3", ".m4a", ".opus", ".ogg"]
    display_title = title or os.path.basename(filepath)

    stream_url = f"http://127.0.0.1:{port}/media"
    html_content = generate_player_html(stream_url, display_title, is_audio)

    window = webview.create_window(
        title=f"OmniPlayer - {display_title}",
        html=html_content,
        width=880 if not is_audio else 560,
        height=580 if not is_audio else 480,
        resizable=True,
        background_color="#0b0f19",
    )
    webview.start()


def play_in_background(filepath: str, title: Optional[str] = None):
    """
    Spawns the player in an independent background process so the main
    app interface remains responsive.
    """
    script_path = os.path.abspath(__file__)
    cmd = [sys.executable, script_path, filepath]
    if title:
        cmd.append(title)
    subprocess.Popen(cmd)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        media_title = sys.argv[2] if len(sys.argv) > 2 else None
        launch_player_window(target_path, media_title)
    else:
        print("Usage: python universal_player.py <path_to_media_file> [title]")
