"""
services/ecapa_engine.py
Gate 4: Second Gender Verification using ECAPA-TDNN.

Model: JaesungHuh/voice-gender-classifier
  - Architecture: ECAPA-TDNN (custom PyTorch, uses PyTorchModelHubMixin)
  - Loaded via: ECAPA_gender.from_pretrained("JaesungHuh/voice-gender-classifier")
  - Fine-tuned on VoxCeleb2 dataset
  - Reported accuracy: 98.7% on VoxCeleb1 test split
  - Input: 16kHz mono audio tensor shape (1, samples)
  - Output: logits over [male=0, female=1]
  - Source repo: https://github.com/JaesungHuh/voice-gender-classifier
    (cloned at F:/SafeSpeak-FYP/voice-gender-classifier/)

Loading strategy:
  - Adds the cloned repo to sys.path so `model.py` can be imported
  - Uses `ECAPA_gender.from_pretrained()` which downloads weights via HuggingFace Hub
  - Weights cached to F: drive (hf_cache) — NOT C: drive

ECAPA confidence threshold: 0.70
  Only accept ECAPA "female" label if softmax confidence >= 70%.
"""

import io
import os
import sys
import logging

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_SAMPLE_RATE   = 16000
ECAPA_MIN_CONFIDENCE = 0.70   # Minimum softmax confidence for female label

# ── Path to the cloned ECAPA repo ─────────────────────────────────────────────
_ECAPA_REPO_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..",                # up to fastapi_app/
    "voice-gender-classifier"  # cloned repo
))

# ── Global model singleton ────────────────────────────────────────────────────
_ecapa_model = None


def preload_ecapa() -> None:
    """Called at startup for logging. Actual loading is lazy (first request)."""
    logger.info("[ECAPA] ECAPA-TDNN engine ready. Model loads on first request.")


def _ensure_ecapa_loaded() -> None:
    """
    Lazy-loads ECAPA-TDNN on first API call.
    Imports ECAPA_gender from the cloned repo and downloads weights via HF Hub.
    """
    global _ecapa_model
    if _ecapa_model is not None:
        return  # Already loaded

    # ── Add cloned repo to sys.path so we can import model.py ─────────────────
    if not os.path.isdir(_ECAPA_REPO_DIR):
        raise FileNotFoundError(
            f"ECAPA repo not found at: {_ECAPA_REPO_DIR}\n"
            f"Please clone: git clone https://github.com/JaesungHuh/voice-gender-classifier.git "
            f"into F:/SafeSpeak-FYP/"
        )

    if _ECAPA_REPO_DIR not in sys.path:
        sys.path.insert(0, _ECAPA_REPO_DIR)
        logger.info(f"[ECAPA] Added repo to sys.path: {_ECAPA_REPO_DIR}")

    # ── Import the ECAPA_gender class from the repo's model.py ────────────────
    from model import ECAPA_gender

    logger.info("[ECAPA] Loading ECAPA-TDNN weights from HuggingFace Hub...")
    _ecapa_model = ECAPA_gender.from_pretrained("JaesungHuh/voice-gender-classifier")
    _ecapa_model.eval()
    logger.info("[ECAPA] ECAPA-TDNN model loaded and ready.")


def get_ecapa_gender(audio_bytes: bytes) -> dict:
    """
    Runs ECAPA-TDNN gender classification on raw audio bytes.

    Args:
        audio_bytes: Raw bytes of the audio file (WAV, 16kHz mono preferred)

    Returns:
        {
            "label":       str,   # "female" or "male"
            "confidence":  float, # Softmax probability of predicted label (0.0–1.0)
            "female_pass": bool,  # True if label=female AND confidence >= 0.70
            "error":       str | None
        }
    """
    import torch
    import torch.nn.functional as F

    # ── Ensure model is loaded ────────────────────────────────────────────────
    try:
        _ensure_ecapa_loaded()
    except Exception as e:
        logger.error(f"[ECAPA] Model loading failed: {e}")
        return {
            "label"      : "unknown",
            "confidence" : 0.0,
            "female_pass": False,
            "error"      : f"ECAPA model unavailable: {str(e)}"
        }

    # ── Read audio from bytes ─────────────────────────────────────────────────
    try:
        import soundfile as sf
        audio_buffer = io.BytesIO(audio_bytes)
        audio_array, sample_rate = sf.read(audio_buffer, dtype='float32')
    except Exception as e:
        logger.error(f"[ECAPA] Failed to read audio: {e}")
        return {
            "label"      : "unknown",
            "confidence" : 0.0,
            "female_pass": False,
            "error"      : "Could not read audio file."
        }

    # ── Convert stereo to mono ────────────────────────────────────────────────
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # ── Resample to 16kHz if needed ───────────────────────────────────────────
    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            import librosa
            audio_array = librosa.resample(
                audio_array, orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE
            )
        except Exception as e:
            logger.warning(f"[ECAPA] Resampling failed: {e}. Proceeding.")

    # ── Run ECAPA-TDNN inference ──────────────────────────────────────────────
    try:
        # Model expects: tensor of shape (batch=1, samples)
        signal = torch.tensor(audio_array, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            # forward() returns logits shape: (batch=1, 2)
            # index 0 = male, index 1 = female  (from pred2gender = {0:'male', 1:'female'})
            logits = _ecapa_model(signal)

        # Apply softmax to get probabilities
        probs = F.softmax(logits, dim=-1)[0]  # shape: (2,)

        male_prob   = float(probs[0])
        female_prob = float(probs[1])

        # Determine label and confidence
        if female_prob >= male_prob:
            final_label      = "female"
            final_confidence = female_prob
        else:
            final_label      = "male"
            final_confidence = male_prob

        female_pass = (final_label == "female" and final_confidence >= ECAPA_MIN_CONFIDENCE)

        logger.info(
            f"[ECAPA] Result: {final_label} (conf={final_confidence:.3f}) | "
            f"female={female_prob:.3f}, male={male_prob:.3f} | "
            f"female_pass={female_pass}"
        )

        return {
            "label"      : final_label,
            "confidence" : round(final_confidence, 4),
            "female_pass": female_pass,
            "error"      : None
        }

    except Exception as e:
        logger.error(f"[ECAPA] Inference error: {e}")
        return {
            "label"      : "unknown",
            "confidence" : 0.0,
            "female_pass": False,
            "error"      : f"ECAPA inference failed: {str(e)}"
        }
