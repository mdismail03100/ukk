import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from src.config import (
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    OUTPUT_FPS,
    TEMP_DIR,
    CROP_STYLE,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_ffmpeg_binary() -> str:
    """Returns path to the ffmpeg executable with preference for full-featured builds."""
    # Check explicitly defined env var first
    env_ffmpeg = os.getenv("FFMPEG_PATH")
    if env_ffmpeg and Path(env_ffmpeg).exists():
        return str(Path(env_ffmpeg))

    candidates = [
        # Full essentials build with libass, boxblur, drawtext, gblur
        r"C:\Users\mdism\AndroidStudioProjects\PDM\desktop\bin\ffmpeg.exe",
        # System PATH
        shutil.which("ffmpeg"),
        # Remotion build (fallback)
        r"C:\Users\mdism\OneDrive\Desktop\tools\Ai tool\puzzle-video\node_modules\@remotion\compositor-win32-x64-msvc\ffmpeg.exe",
    ]

    for cand in candidates:
        if cand and Path(cand).exists():
            return str(cand)

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def is_valid_video_file(file_path: Path) -> bool:
    """Verifies that a file is a genuine binary video file and not an HTML webpage or text."""
    p = Path(file_path)
    if not p.exists() or p.stat().st_size < 10000:
        return False
    try:
        with open(p, "rb") as f:
            header = f.read(64)
            if b"<!DOCTYPE" in header or b"<html" in header or b"{" in header[:2]:
                return False
            if b"ftyp" in header or header.startswith(b"\x1a\x45\xdf\xa3") or header.startswith(b"RIFF"):
                return True
        return True
    except Exception:
        return False


def get_media_duration(file_path: Path) -> float:
    """Retrieves duration of an audio or video file in seconds."""
    ffmpeg = get_ffmpeg_binary()
    try:
        cmd = [
            ffmpeg, "-i", str(file_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Parse Duration: 00:00:23.45 from stderr
        for line in result.stderr.splitlines():
            if "Duration:" in line:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
        return 30.0
    except Exception:
        return 30.0


def extract_clip_audio(ffmpeg: str, video_path: Path, output_wav: Path) -> Optional[Path]:
    """Extracts original audio track from a video clip for speech recognition or mixing."""
    cmd = [
        ffmpeg, "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        str(output_wav)
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_wav
    except Exception as e:
        logger.warning(f"Could not extract audio from {video_path.name}: {e}")
        return None


def process_segment(
    ffmpeg: str,
    input_video: Path,
    start_time: float,
    duration: float,
    output_segment: Path,
    crop_style: str = CROP_STYLE,
    color_boost: bool = False
) -> Path:
    """
    Cuts a segment from a raw video and transforms it into 9:16 vertical 1080x1920.
    Supports cinematic 'blur_background' and 'center_crop'.
    """
    boost_filter = ",eq=saturation=1.12:contrast=1.05" if color_boost else ""

    if crop_style == "center_crop":
        # Fill the 1080x1920 frame by scaling and center-cropping
        vf = f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}{boost_filter}"
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start_time:.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(input_video),
            "-vf", vf,
            "-r", str(OUTPUT_FPS),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-an",
            str(output_segment)
        ]
    else:
        # Professional cinematic blurred background layout for YouTube Shorts
        filter_complex = (
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=25:5,eq=brightness=-0.08:contrast=1.05[bg];"
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2{boost_filter}[outv]"
        )
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start_time:.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(input_video),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-r", str(OUTPUT_FPS),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-an",
            str(output_segment)
        ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return output_segment


def build_final_video(
    video_clips: List[Path],
    audio_track: Optional[Path],
    cut_timestamps: List[float],
    subtitle_ass: Optional[Path],
    output_path: Path,
    crop_style: str = CROP_STYLE,
    preserve_dialogue: bool = True
) -> Path:
    """
    Assembles segments synchronized with music beat drops, merges phonk/dialogue soundtrack,
    burns animated ASS captions, and outputs the final 1080x1920 YouTube Short.
    """
    ffmpeg = get_ffmpeg_binary()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter out any invalid/corrupted files
    valid_clips = [v for v in video_clips if is_valid_video_file(v)]
    if not valid_clips:
        raise ValueError("No valid video files found to process. Please ensure clips are actual MP4/MKV files.")
    video_clips = valid_clips

    total_segments = len(cut_timestamps) - 1
    if total_segments <= 0:
        raise ValueError("Invalid cut timestamps: need at least 2 points.")

    logger.info(f"Assembling {total_segments} beat-synced cuts across {len(video_clips)} video source(s)...")

    segment_files: List[Path] = []
    clip_index = 0

    for i in range(total_segments):
        start = cut_timestamps[i]
        end = cut_timestamps[i + 1]
        duration = end - start

        input_clip = video_clips[clip_index % len(video_clips)]
        clip_index += 1

        clip_len = get_media_duration(input_clip)
        seek_start = (i * 2.8) % max(1.0, clip_len - duration - 0.5)

        seg_file = TEMP_DIR / f"seg_{i:03d}.mp4"
        logger.info(f"Rendering cut #{i+1}/{total_segments} [{duration:.2f}s] from {input_clip.name}")

        process_segment(
            ffmpeg=ffmpeg,
            input_video=input_clip,
            start_time=seek_start,
            duration=duration,
            output_segment=seg_file,
            crop_style=crop_style,
            color_boost=True
        )
        segment_files.append(seg_file)

    # Concat demuxer list
    concat_list_file = TEMP_DIR / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for seg in segment_files:
            safe_path = str(seg.resolve()).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    concatenated_raw = TEMP_DIR / "concatenated_raw.mp4"
    logger.info("Concatenating video segments...")
    concat_cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(concatenated_raw)
    ]
    subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    # Determine audio source
    final_duration = cut_timestamps[-1]
    active_audio_track = audio_track

    # If no separate audio track is provided, extract from the main action clip
    if not active_audio_track or not active_audio_track.exists():
        extracted_audio = TEMP_DIR / "primary_dialogue_soundtrack.wav"
        active_audio_track = extract_clip_audio(ffmpeg, video_clips[0], extracted_audio)

    # Escaped subtitle filter
    video_filters = []
    if subtitle_ass and subtitle_ass.exists():
        sub_path_escaped = str(subtitle_ass.resolve()).replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"ass='{sub_path_escaped}'")

    vf_chain = ",".join(video_filters) if video_filters else "null"

    logger.info("Merging audio track and rendering final 1080x1920 Short...")
    final_cmd = [
        ffmpeg, "-y",
        "-i", str(concatenated_raw),
    ]

    if active_audio_track and active_audio_track.exists():
        final_cmd.extend(["-i", str(active_audio_track)])
        final_cmd.extend(["-t", str(final_duration)])
        if video_filters:
            final_cmd.extend(["-vf", ",".join(video_filters)])
        final_cmd.extend([
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            str(output_path)
        ])
    else:
        final_cmd.extend(["-t", str(final_duration)])
        if video_filters:
            final_cmd.extend(["-vf", ",".join(video_filters)])
        final_cmd.extend([
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "20",
            "-an",
            str(output_path)
        ])

    result = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.warning("Subtitle burn failed with filter error, falling back to clean render without subtitle overlay...")
        fallback_cmd = [
            ffmpeg, "-y",
            "-i", str(concatenated_raw),
            "-i", str(active_audio_track),
            "-t", str(final_duration),
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            str(output_path)
        ]
        subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    logger.info(f"Final 9:16 YouTube Short successfully created at: {output_path}")

    # Cleanup temp segments safely
    for seg in segment_files:
        try:
            if seg.exists():
                seg.unlink()
        except Exception:
            pass

    for tmp in [concat_list_file, concatenated_raw]:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass

    return output_path
