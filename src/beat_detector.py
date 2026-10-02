import logging
import subprocess
from pathlib import Path
from typing import List
from src.config import MIN_CLIP_DURATION, MAX_CLIP_DURATION, MAX_VIDEO_DURATION, TEMP_DIR
from src.video_processor import get_ffmpeg_binary

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def detect_beat_timestamps(audio_path: Path, max_duration: float = MAX_VIDEO_DURATION) -> List[float]:
    """
    Analyzes the audio file using Librosa to detect strong musical beats and drops.
    Returns a sorted list of timestamp cut points starting at 0.0s.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info(f"Analyzing beat drops and rhythm from: {audio_path.name}")

    try:
        import librosa
        import numpy as np

        target_file = audio_path
        if audio_path.suffix.lower() in [".mp4", ".mkv", ".mov", ".webm", ".avi"]:
            temp_wav = TEMP_DIR / f"beat_audio_{audio_path.stem[:15]}.wav"
            ffmpeg_bin = get_ffmpeg_binary()
            cmd = [ffmpeg_bin, "-y", "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "22050", str(temp_wav)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and temp_wav.exists():
                target_file = temp_wav

        # Load audio (downsample to 22050Hz for ultra fast processing)
        y, sr = librosa.load(str(target_file), sr=22050, duration=max_duration)
        total_duration = min(librosa.get_duration(y=y, sr=sr), max_duration)

        # Track tempo and beats
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        # Also detect strong onset peaks (musical hits/drops)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            backtrack=False,
            wait=int(sr * 0.8 / 512)
        )
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)

        # Combine beat_times and onset_times, filter by minimum spacing
        combined_times = sorted(np.unique(np.concatenate(([0.0], beat_times, onset_times))))

        filtered_cuts = [0.0]
        for t in combined_times:
            if t <= filtered_cuts[-1]:
                continue
            delta = t - filtered_cuts[-1]
            if delta >= MIN_CLIP_DURATION:
                filtered_cuts.append(float(t))
            elif delta > MAX_CLIP_DURATION:
                # Force an intermediate cut if gap is too long
                filtered_cuts.append(float(filtered_cuts[-1] + 2.0))

        # Ensure final boundary
        if total_duration - filtered_cuts[-1] > 1.0:
            filtered_cuts.append(float(total_duration))
        else:
            filtered_cuts[-1] = float(total_duration)

        bpm_value = float(tempo[0] if isinstance(tempo, (list, np.ndarray)) else tempo)
        logger.info(f"Beat detection complete! Estimated BPM: {bpm_value:.1f}, Total cuts: {len(filtered_cuts) - 1}")
        return filtered_cuts

    except Exception as e:
        logger.warning(f"Librosa beat detection encountered an error ({e}). Using algorithmic fallback intervals.")
        # Fallback to rhythmic 2.0s beat intervals
        cuts = [0.0]
        current = 0.0
        while current + 2.0 < max_duration:
            current += 2.0
            cuts.append(round(current, 2))
        cuts.append(round(max_duration, 2))
        return cuts
