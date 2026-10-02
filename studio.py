"""
YouTube Shorts AI - Interactive Local Web Studio Server
Provides a modern visual interface for browsing clips, choosing edit styles,
previewing 9:16 vertical shorts, and uploading to YouTube.
"""

import json
import logging
import mimetypes
import os
import shutil
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.config import VIDEOS_DIR, MUSIC_DIR, OUTPUT_DIR, TEMP_DIR, CROP_STYLE, YOUTUBE_PRIVACY_STATUS
from src.video_processor import build_final_video, get_ffmpeg_binary, is_valid_video_file
from src.beat_detector import detect_beat_timestamps
from src.subtitle_engine import transcribe_and_generate_subtitles
from src.uploader import upload_youtube_short, check_youtube_auth

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("StudioServer")

PORT = 5050
LATEST_RENDERED_VIDEO = None


class StudioRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-File-Name")
        super().end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Serve Web UI
        if path == "/" or path == "/index.html":
            html_file = ROOT_DIR / "web" / "index.html"
            if html_file.exists():
                content = html_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404, "Web studio HTML not found")
                return

        # API: YouTube Status
        if path == "/api/youtube_status":
            auth_info = check_youtube_auth()
            self.send_json(auth_info)
            return

        # API: List Videos
        if path == "/api/videos":
            videos = []
            if VIDEOS_DIR.exists():
                for f in sorted(VIDEOS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if f.is_file() and f.suffix.lower() in [".mp4", ".mkv", ".mov", ".webm"]:
                        if is_valid_video_file(f):
                            size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                            videos.append({
                                "name": f.name,
                                "size_mb": size_mb,
                                "path": str(f)
                            })
            self.send_json(videos)
            return

        # API: List Music
        if path == "/api/music":
            music_tracks = []
            if MUSIC_DIR.exists():
                for f in sorted(MUSIC_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                    if f.is_file() and f.suffix.lower() in [".mp3", ".wav", ".m4a", ".ogg", ".aac"]:
                        size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                        music_tracks.append({
                            "name": f.name,
                            "size_mb": size_mb,
                            "path": str(f)
                        })
            self.send_json(music_tracks)
            return

        # Serve Video Files (/media/videos/...)
        if path.startswith("/media/videos/"):
            raw_filename = urllib.parse.unquote(path.replace("/media/videos/", ""))
            file_path = VIDEOS_DIR / raw_filename
            self.serve_file(file_path)
            return

        # Serve Music Files (/media/music/...)
        if path.startswith("/media/music/"):
            raw_filename = urllib.parse.unquote(path.replace("/media/music/", ""))
            file_path = MUSIC_DIR / raw_filename
            self.serve_file(file_path)
            return

        # Serve Output Video Files (/media/output/...)
        if path.startswith("/media/output/"):
            raw_filename = urllib.parse.unquote(path.replace("/media/output/", ""))
            file_path = OUTPUT_DIR / raw_filename
            self.serve_file(file_path)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        global LATEST_RENDERED_VIDEO
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8")) if body else {}

        # API: Configure YouTube Credentials
        if path == "/api/youtube_configure":
            client_id = data.get("client_id", "").strip()
            client_secret = data.get("client_secret", "").strip()
            refresh_token = data.get("refresh_token", "").strip()

            env_file = ROOT_DIR / ".env"
            env_content = ""
            if env_file.exists():
                env_content = env_file.read_text(encoding="utf-8")

            lines = [line for line in env_content.splitlines() if not line.startswith("YOUTUBE_")]
            if client_id:
                lines.append(f"YOUTUBE_CLIENT_ID={client_id}")
            if client_secret:
                lines.append(f"YOUTUBE_CLIENT_SECRET={client_secret}")
            if refresh_token:
                lines.append(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
            lines.append("YOUTUBE_PRIVACY_STATUS=public")

            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.environ["YOUTUBE_CLIENT_ID"] = client_id
            os.environ["YOUTUBE_CLIENT_SECRET"] = client_secret
            os.environ["YOUTUBE_REFRESH_TOKEN"] = refresh_token

            auth_check = check_youtube_auth()
            self.send_json({"status": "success", "auth": auth_check})
            return

        # API: Generate Short
        if path == "/api/generate":
            clip_name = data.get("clip")
            music_name = data.get("music")
            style_name = data.get("style", "extraction_neon")
            crop_style = data.get("crop", "blur_background")

            target_clip = VIDEOS_DIR / clip_name if clip_name else None
            if not target_clip or not target_clip.exists():
                self.send_json({"status": "error", "message": "Target clip not found"}, 400)
                return

            target_music = (MUSIC_DIR / music_name) if music_name else None
            if target_music and not target_music.exists():
                target_music = None

            logger.info(f"Studio Trigger: Rendering Short from '{target_clip.name}' (Style: {style_name}, Crop: {crop_style})")

            try:
                # 1. Detect beats (from custom music if selected, otherwise from clip)
                beat_source = target_music if target_music else target_clip
                cut_timestamps = detect_beat_timestamps(beat_source)

                # 2. Subtitles
                ass_path = TEMP_DIR / "studio_captions.ass"
                subtitle_file = transcribe_and_generate_subtitles(
                    media_file=target_clip,
                    output_ass_path=ass_path,
                    style_name=style_name
                )

                # 3. Final Output Render
                output_name = f"short_{target_clip.stem[:20]}_{style_name}.mp4"
                output_path = OUTPUT_DIR / output_name

                final_path = build_final_video(
                    video_clips=[target_clip],
                    audio_track=target_music,
                    cut_timestamps=cut_timestamps,
                    subtitle_ass=subtitle_file,
                    output_path=output_path,
                    crop_style=crop_style,
                )

                LATEST_RENDERED_VIDEO = final_path

                self.send_json({
                    "status": "success",
                    "output": str(final_path),
                    "output_filename": output_name
                })
            except Exception as e:
                logger.error(f"Render generation failed: {e}", exc_info=True)
                self.send_json({"status": "error", "message": str(e)}, 500)
            return

        # API: 100% Autonomous Bot Trigger
        if path == "/api/autopilot":
            try:
                from src.autopilot import run_autonomous_generation_and_upload
                logger.info("Web Studio Trigger: Running 100% Autonomous AutoPilot...")
                res = run_autonomous_generation_and_upload()
                self.send_json({"status": "success", "result": res})
            except Exception as e:
                logger.error(f"AutoPilot failed: {e}", exc_info=True)
                self.send_json({"status": "error", "message": str(e)}, 500)
            return

        # API: Upload File from Browser
        if path == "/api/upload_file":
            import time
            filename = self.headers.get("X-File-Name", f"upload_{int(time.time())}.mp4")
            filename = urllib.parse.unquote(filename)
            is_music = filename.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac"))
            target_folder = MUSIC_DIR if is_music else VIDEOS_DIR
            dest_file = target_folder / filename

            with open(dest_file, "wb") as f:
                f.write(body)

            logger.info(f"File uploaded via Studio UI: {dest_file.name}")
            self.send_json({"status": "success", "filename": dest_file.name, "type": "music" if is_music else "video"})
            return

        # API: Download from URL
        if path == "/api/download_url":
            url = data.get("url")
            is_audio = data.get("is_audio", False)
            if not url:
                self.send_json({"status": "error", "message": "URL is required"}, 400)
                return

            try:
                from src.downloader import download_media_from_url
                saved_file = download_media_from_url(url, is_audio=is_audio)
                self.send_json({"status": "success", "filename": saved_file.name})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)}, 500)
            return

        # API: Upload to YouTube
        if path == "/api/upload":
            target = LATEST_RENDERED_VIDEO
            if not target or not target.exists():
                # Pick latest in output dir if available
                outputs = list(OUTPUT_DIR.glob("*.mp4"))
                if outputs:
                    target = sorted(outputs, key=lambda f: f.stat().st_mtime, reverse=True)[0]

            if not target or not target.exists():
                self.send_json({
                    "status": "error",
                    "message": "No rendered video found in output/ to upload. Please generate a video first."
                }, 400)
                return

            custom_title = data.get("title", "Action Short 🔥 #Shorts")
            privacy_status = data.get("privacy", "public")

            try:
                result = upload_youtube_short(
                    video_path=target,
                    title=custom_title,
                    privacy_status=privacy_status
                )
                self.send_json({
                    "status": "success",
                    "url": result["url"],
                    "video_id": result["id"]
                })
            except Exception as e:
                logger.error(f"YouTube upload error: {e}")
                self.send_json({
                    "status": "notice",
                    "message": f"YouTube upload error: {e}. Please check your credentials in .env or run scripts/generate_token.py."
                })
            return

        self.send_error(404, "Endpoint not found")

    def serve_file(self, file_path: Path):
        if not file_path.exists():
            self.send_error(404, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "video/mp4"

        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        # Range request support for smooth HTML5 video/audio playback and scrubbing
        if range_header:
            range_match = range_header.replace("bytes=", "").split("-")
            start = int(range_match[0])
            end = int(range_match[1]) if range_match[1] else file_size - 1
            length = end - start + 1

            self.send_response(206)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(length))
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

    def send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, StudioRequestHandler)
    print("=" * 65)
    print(f"  🎬 ShortsAI Studio is LIVE at: http://localhost:{PORT}")
    print("=" * 65)
    print(f"Open http://localhost:{PORT} in your browser to view and edit your clips!")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ShortsAI Studio.")
        httpd.server_close()


if __name__ == "__main__":
    main()
