import os
from pathlib import Path
# Load local .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
VIDEOS_DIR = ASSETS_DIR / "videos"
MUSIC_DIR = ASSETS_DIR / "music"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"

# Ensure runtime directories exist
for folder in [ASSETS_DIR, VIDEOS_DIR, MUSIC_DIR, FONTS_DIR, OUTPUT_DIR, TEMP_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Video Formatting (YouTube Shorts 9:16 ratio)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30
MAX_VIDEO_DURATION = 58.0  # Seconds (under 60s for YouTube Shorts)

# Video layout style: 'blur_background' or 'center_crop'
CROP_STYLE = os.getenv("CROP_STYLE", "blur_background")

# Audio & Beat-Sync Settings
MIN_CLIP_DURATION = 1.6  # Minimum seconds per cut
MAX_CLIP_DURATION = 4.2  # Maximum seconds before forcing a cut
BEAT_SENSITIVITY = 1.0   # Librosa onset strength factor

# Subtitle / Captioning Settings
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "Arial-Bold")
SUBTITLE_FONT_SIZE = 72
# ASS color codes are in &HAABBGGRR format
SUBTITLE_PRIMARY_COLOR = "&H0000FFFF"  # Vibrant Yellow
SUBTITLE_OUTLINE_COLOR = "&H00000000"  # Solid Black
SUBTITLE_OUTLINE_WIDTH = 4.5
SUBTITLE_SHADOW_DEPTH = 2.0
SUBTITLE_ALIGNMENT = 2  # 2 = Bottom-center, 5 = Dead-center

# YouTube Data API Settings
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_PRIVACY_STATUS = os.getenv("YOUTUBE_PRIVACY_STATUS", "public")

# Default Metadata Templates
VIDEO_TITLE_PREFIX = os.getenv("VIDEO_TITLE_PREFIX", "Unstoppable Action Scene 🔥")
VIDEO_TAGS = os.getenv(
    "VIDEO_TAGS",
    "shorts,action,phonk,badass,cinematic,viral,fyp,movieclips"
).split(",")
