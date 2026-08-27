"""
services/aasist_engine.py
AI Voice Spoof Detection using AASIST-L pretrained model.

Pipeline Role:
  This is Step 1 in the voice verification pipeline.
  It runs BEFORE the gender check.

  If AASIST-L detects a spoofed (AI-generated) voice → Reject immediately.
  If AASIST-L detects a genuine (real human) voice   → Pass to gender check.

Model: AASIST-L (Lightweight version)
  - Paper: AASIST: Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks
  - Repo:  https://github.com/clovaai/aasist
  - Weights: Pretrained on ASVspoof2019-LA dataset (included in the repo)
  - Parameters: 85,306 (very lightweight — perfect for CPU inference)
  - EER: 0.99%  |  min t-DCF: 0.0309

Audio Input Requirements:
  - Sample Rate: 16000 Hz (16kHz)
  - Duration: up to 4 seconds (model was trained on 4s clips)
    Longer audio will be trimmed; shorter audio will be zero-padded.
  - Channels: Mono (single channel)

Output:
  - "bonafide" (genuine human voice) → score > 0 → allow
  - "spoof"    (AI/synthetic voice)  → score ≤ 0 → reject
"""

import os
import io
import sys
import logging

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_SAMPLE_RATE = 16000
MAX_AUDIO_SAMPLES  = 64600   # 4.04 seconds at 16kHz (AASIST training standard)

# Path to the cloned AASIST repo — it sits inside the fastapi_app directory now
_REPO_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # .../fastapi_app/app/services/
    "..", "..",                                   # go up to fastapi_app/
    "aasist"                                     # the cloned repo folder
)
_REPO_DIR = os.path.normpath(_REPO_DIR)

# Path to the pretrained AASIST-L weights inside the repo
_WEIGHTS_PATH = os.path.join(_REPO_DIR, "models", "weights", "AASIST-L.pth")

# ── Global model singleton ────────────────────────────────────────────────────
_aasist_model = None


def _ensure_aasist_loaded() -> None:
    """
    Lazy-loads the AASIST-L model on the first call.
    Adds the AASIST repo to sys.path so we can import its model architecture.
    """
    global _aasist_model
    if _aasist_model is not None:
        return  # Already loaded

    import torch

    # ── Add the AASIST repo to Python path so we can import its modules ──────
    if _REPO_DIR not in sys.path:
        sys.path.insert(0, _REPO_DIR)
        logger.info(f"[AASIST] Added repo to sys.path: {_REPO_DIR}")

    # Validate repo and weights exist
    if not os.path.isdir(_REPO_DIR):
        raise FileNotFoundError(
            f"AASIST repo not found at: {_REPO_DIR}\n"
            f"Please clone it: git clone https://github.com/clovaai/aasist.git "
            f"into the SafeSpeak-FYP root directory."
        )
    if not os.path.isfile(_WEIGHTS_PATH):
        raise FileNotFoundError(
            f"AASIST-L weights not found at: {_WEIGHTS_PATH}\n"
            f"The pretrained weights should be included in the cloned repo at "
            f"aasist/models/weights/AASIST-L.pth"
        )

    # ── Import model architecture from the AASIST repo ───────────────────────
    try:
        from models.AASIST import Model as AASISTModel
    except ImportError as e:
        raise ImportError(
            f"Could not import AASIST model architecture: {e}\n"
            f"Make sure the repo is cloned correctly at: {_REPO_DIR}"
        )

    # ── Build model config (exactly matching config/AASIST-L.conf) ──────────
    d_args = {
        "nb_samp"     : 64600,                                       # 4.04s at 16kHz
        "first_conv"  : 128,
        "filts"       : [70, [1, 32], [32, 32], [32, 24], [24, 24]],  # AASIST-L.conf
        "gat_dims"    : [24, 32],                                    # AASIST-L.conf
        "pool_ratios" : [0.4, 0.5, 0.7, 0.5],                       # AASIST-L.conf
        "temperatures": [2.0, 2.0, 100.0, 100.0],
    }

    logger.info("[AASIST] Loading AASIST-L pretrained model...")
    model = AASISTModel(d_args)

    # Load pretrained weights (CPU-only, safe for Azure B2)
    state_dict = torch.load(_WEIGHTS_PATH, map_location="cpu")
    model.load_state_dict(state_dict)
    model.eval()

    _aasist_model = model
    logger.info("[AASIST] AASIST-L model loaded successfully. Ready for inference.")


def check_ai_voice(audio_bytes: bytes) -> dict:
    """
    Runs AASIST-L anti-spoofing detection on the given audio bytes.

    Args:
        audio_bytes: Raw bytes of an audio file (WAV preferred, 16kHz mono)

    Returns:
        {
            "is_spoof":    bool,   # True = AI voice detected, False = real human
            "spoof_score": float,  # Raw model score (negative = spoof, positive = bonafide)
            "label":       str,    # "bonafide" or "spoof"
        }
    """
    import torch
    import numpy as np

    # ── Step 1: Ensure model is loaded ───────────────────────────────────────
    _ensure_aasist_loaded()

    # ── Step 2: Read audio from bytes ────────────────────────────────────────
    try:
        import soundfile as sf
        audio_buffer = io.BytesIO(audio_bytes)
        audio_array, sample_rate = sf.read(audio_buffer, dtype='float32')
    except Exception as e:
        logger.error(f"[AASIST] Failed to read audio bytes: {e}")
        # If we can't read the audio, fail safe — do not block user
        return {"is_spoof": False, "spoof_score": 1.0, "label": "bonafide"}

    # ── Step 3: Convert stereo to mono ───────────────────────────────────────
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # ── Step 4: Resample to 16kHz if needed ──────────────────────────────────
    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            import librosa
            audio_array = librosa.resample(
                audio_array, orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE
            )
            logger.info(f"[AASIST] Resampled from {sample_rate}Hz → 16000Hz")
        except Exception as e:
            logger.warning(f"[AASIST] Resampling failed ({e}), proceeding anyway.")

    # ── Step 5: Trim or pad to exactly MAX_AUDIO_SAMPLES ─────────────────────
    if len(audio_array) > MAX_AUDIO_SAMPLES:
        audio_array = audio_array[:MAX_AUDIO_SAMPLES]
        logger.info(f"[AASIST] Audio trimmed to {MAX_AUDIO_SAMPLES} samples (4.04s)")
    elif len(audio_array) < MAX_AUDIO_SAMPLES:
        pad_length = MAX_AUDIO_SAMPLES - len(audio_array)
        audio_array = np.pad(audio_array, (0, pad_length), mode='constant')
        logger.info(f"[AASIST] Audio zero-padded to {MAX_AUDIO_SAMPLES} samples")

    # ── Step 6: Convert to tensor and run AASIST-L inference ─────────────────
    try:
        # Shape: (batch=1, samples)
        x = torch.tensor(audio_array, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            # AASIST model returns: (_, output) where output shape is (batch, 2)
            # output[:, 0] = spoof score, output[:, 1] = bonafide score
            _, output = _aasist_model(x)

        # Score interpretation:
        # output[0][1] - output[0][0] > 0 → bonafide (real voice)
        # output[0][1] - output[0][0] ≤ 0 → spoof    (AI voice)
        spoof_score = float(output[0][1] - output[0][0])
        is_spoof    = spoof_score <= 0

        label = "spoof" if is_spoof else "bonafide"
        logger.info(f"[AASIST] Result: {label} | score={spoof_score:.4f}")

        return {
            "is_spoof"   : is_spoof,
            "spoof_score": round(spoof_score, 4),
            "label"      : label,
        }

    except Exception as e:
        logger.error(f"[AASIST] Inference error: {e}")
        # Fail safe — if AASIST crashes, don't block legitimate users
        return {"is_spoof": False, "spoof_score": 0.0, "label": "bonafide"}
