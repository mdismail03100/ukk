"""
100% Autonomous Zero-Touch YouTube Shorts Engine
Automatically finds clips, downloads trending tracks, generates viral hooks/captions,
beat-syncs, renders 1080x1920 9:16 vertical video, and uploads on USA schedule.
"""

import json
import logging
import os
import random
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.config import (
    VIDEOS_DIR,
    MUSIC_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    YOUTUBE_PRIVACY_STATUS,
    CROP_STYLE,
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
)
from src.beat_detector import detect_beat_timestamps
from src.subtitle_engine import format_ass_timestamp, generate_ass_header
from src.video_processor import build_final_video, get_ffmpeg_binary, is_valid_video_file
from src.uploader import upload_youtube_short

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("AutoPilot")

# Viral US Audience Niches & Queries
VIRAL_NICHES = [
    {
        "niche": "supercar_phonk",
        "search_query": "supercar drift cinematic 4k",
        "title_templates": [
            "WHEN THE PHONK KICKS IN AT 200 MPH 💀⚡ #Shorts #Phonk #Supercar",
            "Midnight Drift In Tokyo 🏎️💨 #Shorts #Drift #Cars #Viral",
            "Pure Adrenaline & Horsepower 🔥 #Shorts #Supercars #Speed",
            "Wait For The Turbo Spool 😈 #Shorts #CarEdit #Phonk",
        ],
        "hooks": [
            ["DON'T BLINK", "WATCH THIS", "FULL THROTTLE"],
            ["SPEED IS ADDICTIVE", "WHEN BASS DROPS", "UNSTOPPABLE"],
            ["BORN TO RACE", "NO LIMITS", "MAX SPEED"]
        ],
        "tags": ["shorts", "phonk", "supercars", "caredit", "drift", "usa", "fyp", "viral"]
    },
    {
        "niche": "sigma_discipline",
        "search_query": "gym motivation boxing cinematic",
        "title_templates": [
            "RULE #1: NEVER BE WEAK 💀🔥 #Shorts #Sigma #Motivation",
            "THEY DOUBTED. NOW THEY WATCH ⚡ #Shorts #Discipline #Mindset",
            "PAIN IS TEMPORARY. GLORY IS FOREVER 🏆 #Shorts #Gym #Motivation",
            "SILENT IN THE ROOM. DEADLY IN THE RING 🥊 #Shorts #SigmaMale",
        ],
        "hooks": [
            ["NO EXCUSES", "KEEP GRINDING", "BEAT THE ODDS"],
            ["DISCIPLINE BEATS MOTIVATION", "EVERY SINGLE DAY", "STAND ALONE"],
            ["WORK IN SILENCE", "LET SUCCESS", "MAKE THE NOISE"]
        ],
        "tags": ["shorts", "sigma", "motivation", "discipline", "mindset", "gym", "usa", "viral"]
    },
    {
        "niche": "cinema_action",
        "search_query": "cinematic action movie scene 4k",
        "title_templates": [
            "THE BADASST ACTION MOMENT EVER 💀🔥 #Shorts #Action #Cinema",
            "NEVER MESS WITH HIM ⚡ #Shorts #MovieClips #Badass",
            "ONE MAN AGAINST AN ARMY 💥 #Shorts #ActionMovie #Viral",
        ],
        "hooks": [
            ["YOU PICKED", "THE WRONG ENEMY", "NOW PAY"],
            ["SURVIVAL IS NOT AN OPTION", "IT'S A GUARANTEE", "FULL FORCE"],
            ["GET READY", "FOR THE IMPACT", "BASS DROP"]
        ],
        "tags": ["shorts", "action", "movieclips", "cinematic", "badass", "usa", "fyp"]
    }
]

# Royalty-free curated phonk and action tracks for fallback
ROYALTY_FREE_PHONK_TRACKS = [
    "https://raw.githubusercontent.com/mdism/assets/main/drift_phonk_1.mp3",
    "https://raw.githubusercontent.com/mdism/assets/main/aggressive_phonk.mp3"
]


def auto_fetch_video_clips(query: str, count: int = 2) -> List[Path]:
    """
    Automatically fetches high quality action/car clips.
    First checks if Pexels API key is present. If not, uses yt-dlp to search Creative Commons clips,
    or picks from existing library.
    """
    logger.info(f"Auto-Sourcing video clips for niche query: '{query}'...")
    downloaded_clips: List[Path] = []

    # 1. Check Pexels API (if user set PEXELS_API_KEY in secrets)
    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        try:
            req = urllib.request.Request(
                f"https://api.pexels.com/videos/search?query={urllib.request.quote(query)}&per_page={count}&orientation=portrait",
                headers={"Authorization": pexels_key, "User-Agent": "AutoPilot/1.0"}
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                for vid in data.get("videos", []):
                    # Pick 1080p vertical file
                    video_files = vid.get("video_files", [])
                    best_file = next((f for f in video_files if f.get("width") == 1080 and f.get("height") == 1920), video_files[0])
                    video_url = best_file["link"]
                    save_path = VIDEOS_DIR / f"auto_{vid['id']}.mp4"
                    logger.info(f"Downloading Pexels clip: {save_path.name}")
                    urllib.request.urlretrieve(video_url, save_path)
                    downloaded_clips.append(save_path)
            if downloaded_clips:
                return downloaded_clips
        except Exception as e:
            logger.warning(f"Pexels fetch failed ({e}). Falling back to yt-dlp / local library.")

    # 2. Try yt-dlp creative commons search
    try:
        import yt_dlp
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(VIDEOS_DIR / "auto_clip_%(id)s.mp4"),
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 25 * 1024 * 1024,  # Cap at 25MB
            "match_filter": yt_dlp.utils.match_filter_func("duration < 60"),
        }
        search_target = f"ytsearch{count}:{query} shorts creative commons no copyright"
        logger.info(f"Searching Creative Commons clips via yt-dlp: '{search_target}'")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            for entry in info.get("entries", []):
                clip_path = VIDEOS_DIR / f"auto_clip_{entry['id']}.mp4"
                if clip_path.exists():
                    downloaded_clips.append(clip_path)
        if downloaded_clips:
            return downloaded_clips
    except Exception as e:
        logger.warning(f"yt-dlp auto-search note: {e}. Using library pool.")

    # 3. Fallback: Select from local assets library
    existing = [v for v in (list(VIDEOS_DIR.glob("*.mp4")) + list(VIDEOS_DIR.glob("*.mkv"))) if is_valid_video_file(v)]
    if existing:
        selected = random.sample(existing, min(count, len(existing)))
        logger.info(f"Using {len(selected)} valid clip(s) from asset library.")
        return selected

    raise RuntimeError("No valid video source could be fetched or found in assets/videos!")


def auto_fetch_phonk_soundtrack() -> Path:
    """
    Selects or downloads high-energy phonk soundtrack.
    """
    existing_music = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
    if existing_music:
        return random.choice(existing_music)

    # If assets/videos has clips with audio, use that audio
    existing_videos = [v for v in list(VIDEOS_DIR.glob("*.mp4")) if is_valid_video_file(v)]
    if existing_videos:
        extracted = TEMP_DIR / "auto_extracted_soundtrack.wav"
        ffmpeg = get_ffmpeg_binary()
        cmd = [ffmpeg, "-y", "-i", str(existing_videos[0]), "-vn", "-ac", "2", "-ar", "44100", str(extracted)]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return extracted

    # Generate synthetic phonk bass pulse if completely empty
    ffmpeg = get_ffmpeg_binary()
    synth_path = MUSIC_DIR / "auto_phonk_synth.wav"
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=80:duration=45",
        "-c:a", "pcm_s16le",
        str(synth_path)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return synth_path


def create_kinetic_ass_captions(hook_lines: List[str], cut_timestamps: List[float], output_ass: Path) -> Path:
    """
    Generates high-impact glowing ASS captions for the autonomous video.
    """
    header = f"""[Script Info]
Title: AutoPilot Viral Captions
ScriptType: v4.00+
PlayResX: {OUTPUT_WIDTH}
PlayResY: {OUTPUT_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: NeonGlow,Arial-Bold,76,&H00FFFFFF,&H000000FF,&H00D02090,&H80000000,-1,0,0,0,105,105,0,0,1,5.0,3.0,2,40,40,280,1
Style: YellowPop,Arial-Bold,76,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,105,105,0,0,1,5.0,2.0,2,40,40,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(header)

        # Space out hook phrases across the video cuts
        num_phrases = len(hook_lines)
        if len(cut_timestamps) > 2:
            step = max(1, (len(cut_timestamps) - 1) // (num_phrases + 1))
            for idx, phrase in enumerate(hook_lines):
                cut_idx = min(len(cut_timestamps) - 2, 1 + idx * step)
                start_t = format_ass_timestamp(cut_timestamps[cut_idx])
                end_t = format_ass_timestamp(min(cut_timestamps[-1], cut_timestamps[cut_idx] + 2.5))
                style = "YellowPop" if idx % 2 == 1 else "NeonGlow"
                f.write(f"Dialogue: 0,{start_t},{end_t},{style},,0,0,0,,{{\\b1}}{phrase}\n")

    return output_ass


def run_autonomous_generation_and_upload():
    """
    Main entrypoint for 100% hands-free autonomous cloud / local run.
    """
    logger.info("======================================================")
    logger.info("  🚀 Starting 100% Autonomous YouTube Shorts Bot       ")
    logger.info("  Target Audience: USA Peak Viewership Hours          ")
    logger.info("======================================================")

    # 1. Select random high-performing US niche
    niche_config = random.choice(VIRAL_NICHES)
    logger.info(f"Targeted Niche: {niche_config['niche'].upper()}")

    # 2. Automatically source video clips
    clips = auto_fetch_video_clips(niche_config["search_query"], count=2)
    logger.info(f"Sourced {len(clips)} clip(s) for editing.")

    # 3. Automatically source background phonk soundtrack
    soundtrack = auto_fetch_phonk_soundtrack()
    logger.info(f"Soundtrack ready: {soundtrack.name}")

    # 4. Beat and Drop Tracking
    cut_timestamps = detect_beat_timestamps(soundtrack)

    # 5. Generate Viral Kinetic Captions
    hooks = random.choice(niche_config["hooks"])
    ass_path = TEMP_DIR / "auto_captions.ass"
    subtitle_file = create_kinetic_ass_captions(hooks, cut_timestamps, ass_path)

    # 6. Render 1080x1920 9:16 Vertical Short
    output_filename = f"auto_{niche_config['niche']}_{random.randint(1000, 9999)}.mp4"
    output_path = OUTPUT_DIR / output_filename

    build_final_video(
        video_clips=clips,
        audio_track=soundtrack,
        cut_timestamps=cut_timestamps,
        subtitle_ass=subtitle_file,
        output_path=output_path,
        crop_style="center_crop"
    )

    logger.info(f"Autonomous Video Render Complete: {output_path}")

    # 7. Auto-Generate Title & SEO Description
    video_title = random.choice(niche_config["title_templates"])
    description = (
        f"{video_title}\n\n"
        "High energy cinematic edit synced to the beat.\n"
        "Subscribe for daily badass edits and phonk vibes!\n\n"
        "#Shorts #YouTubeShorts #USA #Trending #Viral #Phonk #FYP #Action"
    )
    tags = niche_config["tags"]

    # 8. Automated Headless Upload to YouTube
    logger.info("Starting automated upload to YouTube Shorts...")
    try:
        res = upload_youtube_short(
            video_path=output_path,
            title=video_title,
            description=description,
            tags=tags,
            privacy_status=YOUTUBE_PRIVACY_STATUS
        )
        logger.info("======================================================")
        logger.info(f"🎉 SUCCESS! Published YouTube Short: {res['url']}")
        logger.info("======================================================")
        return res
    except Exception as e:
        logger.error(f"Upload step note: {e}")
        logger.info("Video is rendered and safely saved in output/ directory.")
        return {"status": "rendered", "file": str(output_path)}


if __name__ == "__main__":
    run_autonomous_generation_and_upload()
