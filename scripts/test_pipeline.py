"""
Pipeline Self-Test & Sample Generator Script
Verifies all dependencies, tests FFmpeg execution, and generates synthetic test media.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import VIDEOS_DIR, MUSIC_DIR, OUTPUT_DIR, TEMP_DIR
from src.video_processor import get_ffmpeg_binary


def check_dependencies():
    print("1. Checking Python Libraries...")
    libs = [
        ("librosa", "Audio beat analysis"),
        ("faster_whisper", "Whisper AI speech recognition"),
        ("googleapiclient", "YouTube Data API v3"),
        ("google_auth_oauthlib", "Google OAuth2 client"),
        ("dotenv", "Environment variable loader"),
    ]

    for mod, desc in libs:
        try:
            __import__(mod)
            print(f"   [OK] {mod:<22} : {desc}")
        except ImportError:
            print(f"   [MISSING] {mod:<18} : Run 'pip install -r requirements.txt'")

    print("\n2. Checking FFmpeg...")
    ffmpeg_bin = get_ffmpeg_binary()
    try:
        res = subprocess.run([ffmpeg_bin, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first_line = res.stdout.splitlines()[0] if res.stdout else "Available"
        print(f"   [OK] FFmpeg found: {ffmpeg_bin} ({first_line})")
    except Exception as e:
        print(f"   [WARNING] FFmpeg check failed: {e}")


def generate_sample_media():
    """Generates two short sample video clips and a sample beat audio for testing."""
    ffmpeg = get_ffmpeg_binary()
    print("\n3. Checking / Generating Sample Media...")

    # Generate sample video 1 (testsrc with timestamp)
    sample_vid_1 = VIDEOS_DIR / "sample_action_clip_1.mp4"
    if not sample_vid_1.exists():
        print(f"   Creating test clip 1: {sample_vid_1.name} (5 seconds)...")
        cmd1 = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=6:size=1920x1080:rate=30",
            "-vf", "drawtext=text='ACTION SCENE 1':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(sample_vid_1)
        ]
        try:
            subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            print("   [OK] Test clip 1 created successfully.")
        except Exception as e:
            print(f"   [SKIP] Could not create test clip: {e}")

    # Generate sample video 2
    sample_vid_2 = VIDEOS_DIR / "sample_action_clip_2.mp4"
    if not sample_vid_2.exists():
        print(f"   Creating test clip 2: {sample_vid_2.name} (5 seconds)...")
        cmd2 = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "smptebars=duration=6:size=1920x1080:rate=30",
            "-vf", "drawtext=text='ACTION SCENE 2':fontcolor=yellow:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(sample_vid_2)
        ]
        try:
            subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            print("   [OK] Test clip 2 created successfully.")
        except Exception as e:
            print(f"   [SKIP] Could not create test clip: {e}")

    # Generate sample audio with rhythmic beeps
    sample_audio = MUSIC_DIR / "sample_phonk_beat.wav"
    if not sample_audio.exists():
        print(f"   Creating test beat audio: {sample_audio.name} (6 seconds)...")
        # Synthesize a rhythmic 130 BPM pulse
        cmd_audio = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=110:duration=6",
            "-c:a", "pcm_s16le",
            str(sample_audio)
        ]
        try:
            subprocess.run(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            print("   [OK] Test audio created successfully.")
        except Exception as e:
            print(f"   [SKIP] Could not create test audio: {e}")


def main():
    print("=" * 60)
    print("  YouTube Shorts Automation - Pipeline Diagnostic & Test  ")
    print("=" * 60)
    check_dependencies()
    if "--generate-samples" in sys.argv:
        generate_sample_media()
    else:
        print("\nTip: Run 'python scripts/test_pipeline.py --generate-samples' to automatically create dummy test video/audio files.")
    print("=" * 60)


if __name__ == "__main__":
    main()
