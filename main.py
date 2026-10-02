import argparse
import logging
import os
import random
import sys
from pathlib import Path

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
    CROP_STYLE,
    YOUTUBE_PRIVACY_STATUS,
)
from src.beat_detector import detect_beat_timestamps
from src.subtitle_engine import transcribe_and_generate_subtitles
from src.video_processor import build_final_video
from src.uploader import upload_youtube_short

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ShortsPipeline")


def find_media_files(directory: Path, extensions: tuple) -> list:
    """Finds all files in directory matching the given extensions."""
    if not directory.exists():
        return []
    return [
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    ]


def run_pipeline(
    render_only: bool = False,
    upload_only: str = None,
    crop_style: str = CROP_STYLE,
    custom_title: str = None,
    privacy_status: str = YOUTUBE_PRIVACY_STATUS,
):
    logger.info("==================================================")
    logger.info("   YouTube Shorts AI Automation Pipeline          ")
    logger.info("==================================================")

    # If upload-only is specified
    if upload_only:
        target_video = Path(upload_only)
        if not target_video.exists():
            logger.error(f"Target video file not found: {target_video}")
            sys.exit(1)
        logger.info(f"Direct upload mode enabled for: {target_video.name}")
        upload_youtube_short(
            video_path=target_video,
            title=custom_title,
            privacy_status=privacy_status
        )
        return

    # Step 1: Scan input assets
    video_extensions = (".mp4", ".mkv", ".mov", ".webm", ".avi")
    audio_extensions = (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")

    raw_videos = find_media_files(VIDEOS_DIR, video_extensions)
    music_tracks = find_media_files(MUSIC_DIR, audio_extensions)

    if not raw_videos:
        logger.info(f"No video files found in '{VIDEOS_DIR}'. Switching to Autonomous AutoPilot...")
        from src.autopilot import run_autonomous_generation_and_upload
        run_autonomous_generation_and_upload()
        return

    if not music_tracks:
        logger.info(f"No standalone music found in '{MUSIC_DIR}'. Using audio from video or phonk generator.")
        try:
            from src.autopilot import auto_fetch_phonk_soundtrack
            chosen_audio = auto_fetch_phonk_soundtrack()
        except Exception:
            chosen_audio = None
    else:
        chosen_audio = random.choice(music_tracks)

    logger.info(f"Selected Soundtrack: {chosen_audio.name if chosen_audio else 'Original Clip Audio'}")
    logger.info(f"Available Video Sources: {len(raw_videos)} clip(s)")

    # Step 2: Beat & Drop Detection
    logger.info("--- Step 1/4: Analyzing Audio Beats & Drops ---")
    cut_timestamps = detect_beat_timestamps(chosen_audio)
    logger.info(f"Generated {len(cut_timestamps)} beat sync points.")

    # Step 3: Subtitle Generation (Whisper AI)
    logger.info("--- Step 2/4: Transcribing Dialogue & Generating Captions ---")
    subtitle_ass_path = TEMP_DIR / "captions.ass"
    # Check the first raw video or concatenated dialogue for speech
    subtitle_file = transcribe_and_generate_subtitles(
        media_file=raw_videos[0],
        output_ass_path=subtitle_ass_path
    )

    # Step 4: Video Processing & Rendering
    logger.info("--- Step 3/4: Rendering 9:16 Beat-Synced Vertical Video ---")
    output_filename = f"short_{chosen_audio.stem}_{random.randint(1000, 9999)}.mp4"
    final_output_path = OUTPUT_DIR / output_filename

    build_final_video(
        video_clips=raw_videos,
        audio_track=chosen_audio,
        cut_timestamps=cut_timestamps,
        subtitle_ass=subtitle_file,
        output_path=final_output_path,
        crop_style=crop_style,
    )

    logger.info(f"Render completed: {final_output_path}")

    # Step 5: YouTube Upload
    if render_only:
        logger.info("Render-only flag enabled. Skipping YouTube upload.")
        logger.info(f"Final video ready at: {final_output_path.resolve()}")
        return

    logger.info("--- Step 4/4: Uploading to YouTube Shorts ---")
    try:
        upload_result = upload_youtube_short(
            video_path=final_output_path,
            title=custom_title,
            privacy_status=privacy_status,
        )
        logger.info("==================================================")
        logger.info("Pipeline completed successfully!")
        logger.info(f"YouTube Short URL: {upload_result['url']}")
        logger.info("==================================================")
    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        logger.info("The rendered video is safely saved in the output directory.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Automated YouTube Shorts AI Pipeline")
    parser.add_argument("--autopilot", action="store_true", help="Run 100% autonomous video sourcing, rendering, and upload")
    parser.add_argument("--render-only", action="store_true", help="Render video without uploading to YouTube")
    parser.add_argument("--upload-only", type=str, default=None, help="Upload an existing video file directly")
    parser.add_argument("--crop-style", type=str, choices=["blur_background", "center_crop"], default=CROP_STYLE, help="Video 9:16 layout style")
    parser.add_argument("--title", type=str, default=None, help="Custom video title")
    parser.add_argument("--privacy", type=str, choices=["public", "unlisted", "private"], default=YOUTUBE_PRIVACY_STATUS, help="YouTube upload privacy status")

    args = parser.parse_args()

    if args.autopilot:
        from src.autopilot import run_autonomous_generation_and_upload
        run_autonomous_generation_and_upload()
        return

    run_pipeline(
        render_only=args.render_only,
        upload_only=args.upload_only,
        crop_style=args.crop_style,
        custom_title=args.title,
        privacy_status=args.privacy,
    )


if __name__ == "__main__":
    main()
