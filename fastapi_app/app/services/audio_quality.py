"""
services/audio_quality.py
Gate 1: Audio Quality Validation using Librosa.

Purpose:
  Filters out audio that is too bad to analyze reliably.
  This is NOT an anti-spoof layer — clean audio is NOT flagged as AI.
  Librosa only answers: "Is this audio valid enough to run AI models on?"

Checks performed:
  1. Corrupt / unreadable audio        → Reject (hard fail)
  2. Speech duration < 3 seconds       → Retry
  3. Silence ratio > 45%               → Retry
  4. Clipping ratio > 2%               → Retry
  5. Volume (RMS) too low              → Retry

Outcomes:
  - "ok"     → Audio is valid, proceed to AASIST-L
  - "retry"  → Audio is usable but quality is poor — ask user to re-record
  - "reject" → Audio is corrupt/unreadable — hard fail
"""

import io
import logging

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_SPEECH_SECONDS  = 3.0    # Minimum required speech duration
MAX_SILENCE_RATIO   = 0.45   # Maximum allowed silence fraction (45%)
MAX_CLIPPING_RATIO  = 0.02   # Maximum allowed clipped samples (2%)
MIN_RMS_DB          = -40.0  # Minimum acceptable volume in dBFS
TARGET_SAMPLE_RATE  = 16000  # Resample to this before analysis


def check_audio_quality(audio_bytes: bytes) -> dict:
    """
    Validates raw audio bytes for quality.

    Args:
        audio_bytes: Raw bytes of the uploaded audio file

    Returns:
        {
            "status":          "ok" | "retry" | "reject",
            "message":         str,   # Human-readable reason (for retry/reject)
            "speech_seconds":  float, # Detected speech duration
            "silence_ratio":   float, # Fraction of silence
            "clipping_ratio":  float, # Fraction of clipped samples
            "rms_db":          float, # RMS volume in dBFS
        }
    """
    import numpy as np

    # ── Step 1: Read audio from bytes ─────────────────────────────────────────
    try:
        import soundfile as sf
        audio_buffer = io.BytesIO(audio_bytes)
        audio_array, sample_rate = sf.read(audio_buffer, dtype='float32')
    except Exception as e:
        logger.error(f"[AudioQuality] Cannot read audio file: {e}")
        return {
            "status" : "reject",
            "message": "Audio file is corrupt or unreadable. Please try recording again.",
            "speech_seconds" : 0.0,
            "silence_ratio"  : 1.0,
            "clipping_ratio" : 0.0,
            "rms_db"         : -999.0,
        }

    # ── Step 2: Convert stereo to mono ────────────────────────────────────────
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # ── Step 3: Resample to TARGET_SAMPLE_RATE if needed ──────────────────────
    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            import librosa
            audio_array = librosa.resample(
                audio_array, orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE
            )
            sample_rate = TARGET_SAMPLE_RATE
        except Exception as e:
            logger.warning(f"[AudioQuality] Resampling failed: {e}. Using original rate.")

    total_samples   = len(audio_array)
    total_seconds   = total_samples / sample_rate

    # ── Check 1: Duration (rough total duration check first) ──────────────────
    if total_seconds < MIN_SPEECH_SECONDS:
        logger.info(f"[AudioQuality] Audio too short: {total_seconds:.2f}s")
        return {
            "status" : "retry",
            "message": f"Recording is too short ({total_seconds:.1f}s). Please speak for at least 3 seconds.",
            "speech_seconds" : total_seconds,
            "silence_ratio"  : 0.0,
            "clipping_ratio" : 0.0,
            "rms_db"         : 0.0,
        }

    # ── Check 2: Silence ratio using librosa voice activity ───────────────────
    try:
        import librosa
        # Use librosa's top_db parameter to detect non-silent intervals
        # top_db=30 means sections quieter than 30dB below peak are silent
        non_silent_intervals = librosa.effects.split(audio_array, top_db=30)
        non_silent_samples   = sum(end - start for start, end in non_silent_intervals)
        speech_seconds       = non_silent_samples / sample_rate
        silence_ratio        = 1.0 - (non_silent_samples / total_samples)
    except Exception as e:
        logger.warning(f"[AudioQuality] Silence detection failed: {e}. Using total duration.")
        speech_seconds = total_seconds
        silence_ratio  = 0.0

    if silence_ratio > MAX_SILENCE_RATIO:
        logger.info(f"[AudioQuality] Too much silence: {silence_ratio:.1%}")
        return {
            "status" : "retry",
            "message": "Too much silence detected. Please speak continuously and try again.",
            "speech_seconds" : speech_seconds,
            "silence_ratio"  : round(silence_ratio, 4),
            "clipping_ratio" : 0.0,
            "rms_db"         : 0.0,
        }

    if speech_seconds < MIN_SPEECH_SECONDS:
        logger.info(f"[AudioQuality] Actual speech too short: {speech_seconds:.2f}s")
        return {
            "status" : "retry",
            "message": f"Only {speech_seconds:.1f}s of speech detected. Please read the sentence clearly.",
            "speech_seconds" : speech_seconds,
            "silence_ratio"  : round(silence_ratio, 4),
            "clipping_ratio" : 0.0,
            "rms_db"         : 0.0,
        }

    # ── Check 3: Clipping ratio ────────────────────────────────────────────────
    # Clipping = samples at or above ±1.0 (the maximum for float32 audio)
    clipped_samples = np.sum(np.abs(audio_array) >= 0.999)
    clipping_ratio  = clipped_samples / total_samples

    if clipping_ratio > MAX_CLIPPING_RATIO:
        logger.info(f"[AudioQuality] Audio clipping detected: {clipping_ratio:.2%}")
        return {
            "status" : "retry",
            "message": "Audio is distorted (clipping). Please move away from the mic and try again.",
            "speech_seconds" : speech_seconds,
            "silence_ratio"  : round(silence_ratio, 4),
            "clipping_ratio" : round(clipping_ratio, 4),
            "rms_db"         : 0.0,
        }

    # ── Check 4: Volume (RMS) check ────────────────────────────────────────────
    rms        = np.sqrt(np.mean(audio_array ** 2))
    # Convert to dBFS — add small epsilon to avoid log(0)
    rms_db     = 20 * np.log10(rms + 1e-10)

    if rms_db < MIN_RMS_DB:
        logger.info(f"[AudioQuality] Volume too low: {rms_db:.1f} dBFS")
        return {
            "status" : "retry",
            "message": "Voice is too quiet. Please speak louder or move closer to the mic.",
            "speech_seconds" : speech_seconds,
            "silence_ratio"  : round(silence_ratio, 4),
            "clipping_ratio" : round(clipping_ratio, 4),
            "rms_db"         : round(rms_db, 2),
        }

    # ── All checks passed ─────────────────────────────────────────────────────
    logger.info(
        f"[AudioQuality] OK — speech={speech_seconds:.2f}s, "
        f"silence={silence_ratio:.1%}, clip={clipping_ratio:.2%}, rms={rms_db:.1f}dBFS"
    )
    return {
        "status"        : "ok",
        "message"       : "Audio quality is acceptable.",
        "speech_seconds": round(speech_seconds, 2),
        "silence_ratio" : round(silence_ratio, 4),
        "clipping_ratio": round(clipping_ratio, 4),
        "rms_db"        : round(rms_db, 2),
    }
