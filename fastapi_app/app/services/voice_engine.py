"""
services/voice_engine.py
Core AI engine for Voice Verification — 5-Gate Pipeline.

Pipeline:
  Gate 1 — Librosa audio quality validation (bad audio filter, NOT spoof detection)
  Gate 2 — AASIST-L anti-spoofing (AI/TTS/replay detection)
  Gate 3 — Wav2Vec2 gender score (female probability 0.0-1.0)
  Gate 4 — ECAPA-TDNN gender check (independent second architecture)
  Gate 5 — Conservative dual-model decision policy

Three possible outcomes:
  ✅ Approve  — Both models agree: female voice, genuine human
  ⚠️ Retry   — Models uncertain or disagree (accent, mic, compression)
  ❌ Reject   — Clear spoof OR both models say male

Models Used:
  1. AASIST-L (Anti-Spoofing)
     - Pretrained on ASVspoof2019-LA
     - 85,306 parameters — lightweight, CPU-safe

  2. alefiury/wav2vec2-large-xlsr-53-gender-recognition-librispeech
     - Wav2Vec2 Transformer fine-tuned for gender classification
     - Input: 16kHz mono WAV

  3. JaesungHuh/voice-gender-classifier (ECAPA-TDNN)
     - ECAPA-TDNN fine-tuned on VoxCeleb2 (98.7% accuracy)
     - Independent architecture from Wav2Vec2
"""

import io
import os

# ── Redirect HuggingFace cache to F: drive (NOT C: drive) ────────────────────
if not os.environ.get("HF_HOME"):
    os.environ["HF_HOME"] = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "hf_cache"
    )

import asyncio
import logging
from fastapi import UploadFile

logger = logging.getLogger(__name__)

# ── Wav2Vec2 Model Configuration ──────────────────────────────────────────────
WAV2VEC_MODEL_NAME      = "alefiury/wav2vec2-large-xlsr-53-gender-recognition-librispeech"
TARGET_SAMPLE_RATE      = 16000

# ── Decision Thresholds ───────────────────────────────────────────────────────
# These are calibrated based on real + AI voice testing.
# Wav2Vec2 tends to be conservative — real female voices often score 0.60-0.85.
WAV2VEC_APPROVE_THRESHOLD = 0.75   # female prob >= 0.75 → clear female
WAV2VEC_RETRY_THRESHOLD   = 0.45   # female prob >= 0.45 → uncertain (ask to retry)
WAV2VEC_HARD_REJECT       = 0.30   # female prob <  0.30 → clearly male → permanent reject

# ── Global Wav2Vec2 model singleton ──────────────────────────────────────────
_wav2vec_model     = None
_wav2vec_extractor = None


def preload_models() -> None:
    """Called at FastAPI startup. Actual loading is lazy (first request)."""
    logger.info("[Voice] 5-Gate pipeline ready. Models load on first request.")


# ─────────────────────────────────────────────────────────────────────────────
# Wav2Vec2 — Gate 3
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_wav2vec_loaded() -> None:
    global _wav2vec_model, _wav2vec_extractor
    if _wav2vec_model is not None:
        return

    import torch
    from transformers import Wav2Vec2ForSequenceClassification, AutoFeatureExtractor

    logger.info(f"[Wav2Vec2] Loading model: {WAV2VEC_MODEL_NAME}")
    _wav2vec_extractor = AutoFeatureExtractor.from_pretrained(WAV2VEC_MODEL_NAME)
    _wav2vec_model = Wav2Vec2ForSequenceClassification.from_pretrained(
        WAV2VEC_MODEL_NAME,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
    )
    _wav2vec_model.eval()
    logger.info("[Wav2Vec2] Model loaded and ready.")


def _get_wav2vec_female_prob(audio_array, sample_rate: int) -> float:
    """Returns female probability (0.0 to 1.0) from Wav2Vec2."""
    import torch
    import librosa

    _ensure_wav2vec_loaded()

    # Resample to 16kHz
    if sample_rate != TARGET_SAMPLE_RATE:
        audio_array = librosa.resample(
            audio_array, orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE
        )

    # Stereo to mono
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    inputs = _wav2vec_extractor(
        audio_array,
        sampling_rate=TARGET_SAMPLE_RATE,
        return_tensors="pt",
        padding=True
    )

    with torch.no_grad():
        logits = _wav2vec_model(**inputs).logits

    probabilities = torch.nn.functional.softmax(logits, dim=-1)
    id2label      = _wav2vec_model.config.id2label

    scores = {id2label[i].lower(): probabilities[0][i].item() for i in range(len(id2label))}
    female_prob = scores.get("female", 0.0)

    logger.info(
        f"[Wav2Vec2] female={female_prob:.3f}, male={scores.get('male', 0.0):.3f}"
    )
    return female_prob


# ─────────────────────────────────────────────────────────────────────────────
# Main synchronous pipeline
# ─────────────────────────────────────────────────────────────────────────────
def _run_pipeline_sync(audio_bytes: bytes, face_verified: bool) -> dict:
    """
    Runs the full 5-gate voice verification pipeline synchronously.
    Called inside a thread pool from run_voice_pipeline() to avoid
    blocking the FastAPI async event loop.
    """
    import numpy as np
    import soundfile as sf

    # ── Load audio ────────────────────────────────────────────────────────────
    try:
        audio_buffer = io.BytesIO(audio_bytes)
        audio_array, sample_rate = sf.read(audio_buffer, dtype='float32')
    except Exception as e:
        logger.error(f"[Voice] Failed to read audio: {e}")
        return {
            "success": False,
            "message": "Audio file is corrupt or unreadable. Please try recording again.",
            "retry"  : False,
        }

    # Convert stereo to mono
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # ═════════════════════════════════════════════════════════════════════════
    # GATE 1: Librosa Audio Quality Validation
    # Purpose: Filter out audio too bad to analyze. NOT spoof detection.
    # ═════════════════════════════════════════════════════════════════════════
    try:
        from app.services.audio_quality import check_audio_quality
        quality = check_audio_quality(audio_bytes)

        if quality["status"] == "reject":
            logger.warning(f"[Gate1] Audio rejected — corrupt: {quality['message']}")
            return {
                "success": False,
                "message": quality["message"],
                "retry"  : False,
                "data"   : {"voice_score": 0, "voice_verification": False}
            }

        if quality["status"] == "retry":
            logger.info(f"[Gate1] Audio retry — poor quality: {quality['message']}")
            return {
                "success": False,
                "message": quality["message"],
                "retry"  : True,
                "data"   : {"voice_score": 0, "voice_verification": False}
            }

        logger.info(
            f"[Gate1] Audio OK — speech={quality['speech_seconds']}s, "
            f"silence={quality['silence_ratio']:.1%}, rms={quality['rms_db']}dBFS"
        )
    except Exception as e:
        # Gate 1 failure is non-fatal — log and continue
        logger.error(f"[Gate1] Quality check error: {e}. Proceeding.")

    # Gate 2 (AASIST-L) has been moved down below the gender checks.
    # We want to fail fast for male voices and return "Male voice detected"
    # before we run anti-spoofing checks (which might flag a real male as AI).

    # ═════════════════════════════════════════════════════════════════════════
    # GATE 3: Wav2Vec2 Gender Score
    # ═════════════════════════════════════════════════════════════════════════
    try:
        wav2vec_female_prob = _get_wav2vec_female_prob(audio_array, sample_rate)
    except Exception as e:
        logger.error(f"[Gate3] Wav2Vec2 error: {e}")
        return {
            "success": False,
            "message": f"Voice analysis failed. Error: {str(e)}",
            "retry"  : True,
            "data"   : {"voice_score": 0, "voice_verification": False}
        }

    # Early hard reject — only if CLEARLY male (< 30%) — no need for ECAPA
    # NOTE: 30% threshold is intentionally low to avoid false rejecting genuine females.
    # Real female voices with heavy accents or mic issues can score 35-55%.
    if wav2vec_female_prob < WAV2VEC_HARD_REJECT:
        logger.info(
            f"[Gate3] Wav2Vec2 hard reject — female_prob={wav2vec_female_prob:.3f} < 0.30 (clearly male)"
        )
        return {
            "success": False,
            "message": "Male voice detected. SafeSpeak is for female users only.",
            "retry"  : False,
            "data"   : {
                "voice_score"       : round(wav2vec_female_prob * 100, 2),
                "voice_verification": False,
                "rejection_reason"  : "male_voice_detected"
            }
        }

    # Uncertain zone (30-44%) — do not hard reject, let ECAPA decide
    # This ensures deep-voice females get a fair chance through dual-model check

    # ═════════════════════════════════════════════════════════════════════════
    # GATE 4: ECAPA-TDNN Gender Check (Second independent model)
    # ═════════════════════════════════════════════════════════════════════════
    ecapa_result     = None
    ecapa_available  = True

    try:
        from app.services.ecapa_engine import get_ecapa_gender
        ecapa_result = get_ecapa_gender(audio_bytes)

        if ecapa_result.get("error"):
            logger.warning(f"[Gate4] ECAPA error: {ecapa_result['error']}. Falling back to Wav2Vec2 only.")
            ecapa_available = False
        else:
            logger.info(
                f"[Gate4] ECAPA: label={ecapa_result['label']}, "
                f"conf={ecapa_result['confidence']:.3f}, "
                f"female_pass={ecapa_result['female_pass']}"
            )
    except Exception as e:
        logger.error(f"[Gate4] ECAPA engine unavailable: {e}. Falling back to Wav2Vec2 only.")
        ecapa_available = False

    # ═════════════════════════════════════════════════════════════════════════
    # GATE 2: AASIST-L Anti-Spoof Detection (Moved here)
    # ═════════════════════════════════════════════════════════════════════════
    try:
        from app.services.aasist_engine import check_ai_voice
        spoof_result = check_ai_voice(audio_bytes)

        if spoof_result["is_spoof"]:
            logger.warning(
                f"[Gate2] AASIST-L spoof detected. score={spoof_result['spoof_score']}"
            )
            return {
                "success": False,
                "message": "Male voice detected. ",
                "retry"  : False,
                "data"   : {
                    "voice_score"       : 0,
                    "voice_verification": False,
                    "rejection_reason"  : "male_voice_detected"
                }
            }

        logger.info(
            f"[Gate2] AASIST-L: bonafide. score={spoof_result['spoof_score']}"
        )
    except Exception as e:
        logger.error(f"[Gate2] AASIST-L error: {e}. Skipping anti-spoof check.")

    # ═════════════════════════════════════════════════════════════════════════
    # GATE 5: Conservative Decision Policy
    # ═════════════════════════════════════════════════════════════════════════
    voice_score = round(wav2vec_female_prob * 100, 2)

    # ── Case A: ECAPA is available — dual-model decision ─────────────────────
    if ecapa_available and ecapa_result:
        ecapa_female_pass = ecapa_result["female_pass"]
        ecapa_label       = ecapa_result["label"]

        # ✅ APPROVE: Both models clearly agree female
        if wav2vec_female_prob >= WAV2VEC_APPROVE_THRESHOLD and ecapa_female_pass:
            logger.info("[Gate5] APPROVE — Both models agree: female voice confirmed.")
            return {
                "success": True,
                "message": "Voice verified successfully. Female voice confirmed.",
                "retry"  : False,
                "data"   : {
                    "voice_score"      : voice_score,
                    "voice_verification": True
                }
            }

        # ⚠️ RETRY: Wav2Vec2 uncertain (55-79%) but ECAPA says female
        if wav2vec_female_prob >= WAV2VEC_RETRY_THRESHOLD and ecapa_female_pass:
            logger.info("[Gate5] RETRY — Wav2Vec2 uncertain, ECAPA female. Ask to retry.")
            return {
                "success": False,
                "message": "Voice is unclear. Please speak naturally and try again.",
                "retry"  : True,
                "data"   : {
                    "voice_score"      : voice_score,
                    "voice_verification": False
                }
            }

        # ❌ REJECT: Both models clearly indicate male
        if wav2vec_female_prob < WAV2VEC_HARD_REJECT and ecapa_label == "male":
            logger.info("[Gate5] REJECT — Both models: male voice.")
            return {
                "success": False,
                "message": "Male voice detected. SafeSpeak is for female users only.",
                "retry"  : False,
                "data"   : {
                    "voice_score"       : voice_score,
                    "voice_verification": False,
                    "rejection_reason"  : "male_voice_detected"
                }
            }



        # ❌ REJECT: Models disagree (e.g. low pitch male that fooled Wav2Vec2)
        # Instead of retrying forever, if ECAPA says male, we reject outright.
        logger.info(
            f"[Gate5] REJECT — Models disagree. "
            f"Wav2Vec2={wav2vec_female_prob:.3f}, ECAPA={ecapa_label}({ecapa_result['confidence']:.3f})"
        )
        return {
            "success": False,
            "message": "Male voice detected. SafeSpeak is for female users only.",
            "retry"  : False,
            "data"   : {
                "voice_score"       : voice_score,
                "voice_verification": False,
                "rejection_reason"  : "male_voice_detected"
            }
        }

    # ── Case B: ECAPA unavailable — fall back to Wav2Vec2 only ───────────────
    logger.warning("[Gate5] ECAPA unavailable. Using Wav2Vec2 only (reduced security).")

    if wav2vec_female_prob >= WAV2VEC_APPROVE_THRESHOLD:
        return {
            "success": True,
            "message": "Voice verified successfully. Female voice confirmed.",
            "retry"  : False,
            "data"   : {
                "voice_score"      : voice_score,
                "voice_verification": True
            }
        }

    # Wav2Vec2 in 55-79% range without ECAPA → retry
    return {
        "success": False,
        "message": "Voice is unclear. Please speak naturally and try again.",
        "retry"  : True,
        "data"   : {
            "voice_score"      : voice_score,
            "voice_verification": False
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public async entry point
# ─────────────────────────────────────────────────────────────────────────────
async def run_voice_pipeline(audio_file: UploadFile, face_verified: bool) -> dict:
    """
    Full async entry point for voice verification.
    Reads the uploaded file and runs the 5-gate pipeline in a thread pool.
    """
    try:
        audio_bytes = await audio_file.read()
    except Exception as e:
        logger.error(f"[Voice] Failed to read upload: {e}")
        return {
            "success": False,
            "message": "Failed to read uploaded audio file.",
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _run_pipeline_sync,
        audio_bytes,
        face_verified
    )
