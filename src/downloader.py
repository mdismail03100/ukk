import logging
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional
from src.config import VIDEOS_DIR, MUSIC_DIR

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def download_media_from_url(url: str, is_audio: bool = False, custom_name: Optional[str] = None) -> Path:
    """
    Downloads media from a direct URL or YouTube/Social link.
    Saves to assets/videos or assets/music.
    """
    target_dir = MUSIC_DIR if is_audio else VIDEOS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check if yt-dlp is available for YouTube/TikTok links
    try:
        import yt_dlp

        out_template = str(target_dir / (custom_name or "%(title).50s.%(ext)s"))
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        if is_audio:
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            ydl_opts.update({
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            })

        logger.info(f"Downloading media via yt-dlp: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if is_audio and not filename.endswith(".mp3"):
                filename = re.sub(r"\.[^.]+$", ".mp3", filename)
            logger.info(f"Download complete: {filename}")
            return Path(filename)

    except ImportError:
        # Fallback to standard HTTP stream download for direct mp4/mp3 links
        logger.info(f"yt-dlp not found. Downloading via direct HTTP: {url}")
        clean_name = custom_name or url.split("/")[-1].split("?")[0]
        if not (clean_name.endswith(".mp4") or clean_name.endswith(".mp3")):
            clean_name += ".mp3" if is_audio else ".mp4"

        save_path = target_dir / clean_name
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as response, open(save_path, "wb") as out_file:
            out_file.write(response.read())

        logger.info(f"Direct download complete: {save_path.name}")
        return save_path
