import logging
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from src.config import (
    WHISPER_MODEL,
    SUBTITLE_FONT,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_PRIMARY_COLOR,
    SUBTITLE_OUTLINE_COLOR,
    SUBTITLE_OUTLINE_WIDTH,
    SUBTITLE_SHADOW_DEPTH,
    SUBTITLE_ALIGNMENT,
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    TEMP_DIR,
)
from src.video_processor import get_ffmpeg_binary

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Preset styles inspired by viral movie edits (Extraction 2, Phonk, TikTok)
STYLE_PRESETS = {
    "extraction_neon": {
        "font": "Arial-Bold",
        "size": 74,
        "primary": "&H00FFFFFF",   # Crisp White text
        "outline": "&H00D02090",   # Neon Purple / Violet Glow border
        "border_width": 4.0,
        "shadow": 3.0,
        "alignment": 2,            # Lower-third
        "tag": "ROSHAN EDIT"
    },
    "yellow_pop": {
        "font": "Arial-Bold",
        "size": 72,
        "primary": "&H0000FFFF",   # Vibrant Neon Yellow
        "outline": "&H00000000",   # Deep Solid Black
        "border_width": 4.5,
        "shadow": 2.0,
        "alignment": 2,
        "tag": "ACTION"
    },
    "cyan_cyber": {
        "font": "Arial-Bold",
        "size": 72,
        "primary": "&H00FFFF00",   # Bright Cyan
        "outline": "&H00101010",   # Dark Charcoal
        "border_width": 4.0,
        "shadow": 3.0,
        "alignment": 2,
        "tag": "PHONK"
    },
    "minimal_clean": {
        "font": "Arial-Bold",
        "size": 66,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "border_width": 3.0,
        "shadow": 1.5,
        "alignment": 2,
        "tag": "CINEMA"
    }
}


def format_ass_timestamp(seconds: float) -> str:
    """Converts seconds into ASS timestamp format: H:MM:SS.cs"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def generate_ass_header(style_name: str = "extraction_neon") -> str:
    """Generates the ASS script header with bold stylish typography for Shorts."""
    cfg = STYLE_PRESETS.get(style_name, STYLE_PRESETS["extraction_neon"])

    return f"""[Script Info]
Title: Action Shorts Dynamic Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {OUTPUT_WIDTH}
PlayResY: {OUTPUT_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H000000FF,{cfg['outline']},&H80000000,-1,0,0,0,100,100,0,0,1,{cfg['border_width']},{cfg['shadow']},{cfg['alignment']},40,40,260,1
Style: Highlight,{cfg['font']},{cfg['size'] + 4},&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,105,105,0,0,1,{cfg['border_width'] + 1.0},{cfg['shadow']},{cfg['alignment']},40,40,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def transcribe_and_generate_subtitles(
    media_file: Path,
    output_ass_path: Path,
    model_name: str = WHISPER_MODEL,
    style_name: str = "extraction_neon"
) -> Optional[Path]:
    """
    Extracts speech using faster-whisper and generates a modern animated ASS subtitle file.
    Matches the Extraction 2 / TikTok style with punchy 1-3 word bursts.
    """
    media_file = Path(media_file)
    output_ass_path = Path(output_ass_path)

    logger.info(f"Transcribing dialogue from '{media_file.name}' using Whisper ('{model_name}' model)...")

    try:
        from faster_whisper import WhisperModel
        import soundfile as sf

        # Decode audio to 16kHz mono WAV using full FFmpeg to avoid PyAV 19 metadata_errors bug
        ffmpeg_bin = get_ffmpeg_binary()
        temp_wav = TEMP_DIR / f"whisper_audio_{media_file.stem[:15]}.wav"
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(media_file),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            str(temp_wav)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and temp_wav.exists() and temp_wav.stat().st_size > 1000:
            audio_input, _ = sf.read(str(temp_wav), dtype="float32")
        else:
            audio_input = str(media_file)

        # Run on CPU with int8 quantization
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            audio_input,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
        )

        words_list: List[Dict] = []
        for segment in segments:
            if segment.words:
                for word_info in segment.words:
                    clean_word = re.sub(r"[^\w\s\?\!\'\-]", "", word_info.word).strip().upper()
                    if clean_word:
                        words_list.append({
                            "word": clean_word,
                            "start": word_info.start,
                            "end": word_info.end,
                        })

        if not words_list:
            logger.info("No spoken dialogue detected in this video segment.")
            return None

        logger.info(f"Detected {len(words_list)} spoken words. Applying '{style_name}' kinetic captions...")

        # Group words into snappy 1-3 word punchy bursts
        chunks = []
        current_chunk = []
        chunk_word_limit = 3

        for w in words_list:
            current_chunk.append(w)
            if len(current_chunk) >= chunk_word_limit or (len(current_chunk) > 1 and w["end"] - current_chunk[0]["start"] > 1.2):
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)

        # Write ASS File
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(generate_ass_header(style_name))

            for chunk in chunks:
                start_time = format_ass_timestamp(chunk[0]["start"])
                end_time = format_ass_timestamp(chunk[-1]["end"])
                chunk_text = " ".join([item["word"] for item in chunk])

                # Extraction 2 Style with glowing vertical accent bar
                dialogue_line = (
                    f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,"
                    f"{{\\b1}}{chunk_text}\n"
                )
                f.write(dialogue_line)

        logger.info(f"Subtitles generated successfully at: {output_ass_path.name}")
        return output_ass_path

    except ImportError:
        logger.warning("faster-whisper is not installed. Subtitles generation skipped.")
        return None
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}. Continuing without subtitles.")
        return None
