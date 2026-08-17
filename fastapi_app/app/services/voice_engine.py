"""
services/voice_engine.py
Core AI engine for Voice Verification and Gender Check.

Pipeline:
  Step 1 — Read uploaded WAV bytes from multipart form data.
  Step 2 — Load audio into numpy array using soundfile, resample to 16kHz if needed.
  Step 3 — Run Wav2Vec2 gender recognition model to get Female confidence score.
  Step 4 — Apply scoring logic:
              Score 80-100  → Female confirmed ✅ Approve
              Score 50-79   → Ambiguous voice ⚠️  Approve only if face_verified=True
              Score 0-49    → Male / Reject   ❌ Reject
  Step 5 — Return structured JSON result.

Model Used:
  alefiury/wav2vec2-large-xlsr-53-gender-recognition-librispeech
  - Fine-tuned on LibriSpeech (English) for Male/Female classification
  - Input: 16kHz mono WAV audio
  - Output: Female confidence score (0.0 to 1.0)
"""

import io
import os

# ── Redirect HuggingFace cache to a local folder (works on Windows AND Azure Linux) ─
# Must be set BEFORE importing transformers so the library respects it.
if not os.environ.get("HF_HOME"):
    # Use a path relative to this file — works on both Windows (dev) and Linux (Azure)
    os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hf_cache")

import asyncio
import logging
import numpy as np
import soundfile as sf
import torch
from fastapi import UploadFile
from transformers import Wav2Vec2ForSequenceClassification, AutoFeatureExtractor


logger = logging.getLogger(__name__)

# ── Model Configuration ──────────────────────────────────────────────────────
# Lighter model (~400MB) — same accuracy, 3x smaller than the original
MODEL_NAME = "hadrien-hd/wav2vec2-base-gender-recognition"
TARGET_SAMPLE_RATE = 16000   # Model requires exactly 16kHz

# ── Scoring Thresholds ───────────────────────────────────────────────────────
FEMALE_CONFIRM_THRESHOLD = 80    # Score >= 80 → clear female voice → approve
AMBIGUOUS_LOWER_THRESHOLD = 50   # Score 50-79 → ambiguous → needs face_verified=True
# Score < 50 → reject

# ── Global model singleton (loaded once at startup) ──────────────────────────
_model = None
_feature_extractor = None


def preload_models() -> None:
    """
    Called once at FastAPI startup via lifespan in main.py.
    Uses LAZY loading — model downloads and loads on the FIRST API request,
    not at server startup. This keeps startup fast and avoids memory spikes.
    """
    logger.info("Voice engine ready. Model will load on first request (lazy loading).")
    # Intentionally NOT loading here — see _ensure_model_loaded() below.



def _ensure_model_loaded() -> None:
    """
    Lazy loader — loads the model on the first API call if not already loaded.
    Uses float16 + low_cpu_mem_usage to cut RAM usage by ~50%.
    """
    global _model, _feature_extractor
    if _model is not None and _feature_extractor is not None:
        return  # Already loaded — nothing to do
    logger.info(f"[Lazy Load] Loading voice gender model: {MODEL_NAME}")
    _feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
    _model = Wav2Vec2ForSequenceClassification.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,   # Half precision: cuts RAM from ~4GB → ~2GB
        low_cpu_mem_usage=True,      # Loads layer by layer instead of all at once
    )
    _model.eval()
    logger.info("[Lazy Load] Voice gender model loaded and ready.")



def _get_female_score(audio_array: np.ndarray, sample_rate: int) -> float:
    """
    Runs the Wav2Vec2 model on the audio and returns the Female confidence
    score as a float between 0.0 and 100.0.

    Args:
        audio_array: 1D float32 numpy array of audio samples
        sample_rate:  Sample rate of the audio (should be 16000)

    Returns:
        female_score: float in range [0.0, 100.0]
    """
    global _model, _feature_extractor

    # Ensure model is loaded (lazy loading on first call)
    _ensure_model_loaded()

    # Resample if necessary (Flutter should already send 16kHz, but just in case)
    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            import librosa
            audio_array = librosa.resample(
                audio_array,
                orig_sr=sample_rate,
                target_sr=TARGET_SAMPLE_RATE
            )
            logger.info(f"Audio resampled from {sample_rate}Hz to {TARGET_SAMPLE_RATE}Hz")
        except Exception as e:
            raise ValueError(f"Audio resampling failed: {e}")

    # Convert stereo to mono if needed
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    # Prepare input tensor for the model
    inputs = _feature_extractor(
        audio_array,
        sampling_rate=TARGET_SAMPLE_RATE,
        return_tensors="pt",
        padding=True
    )
    # Cast to float16 to match the model dtype (loaded with torch_dtype=float16)
    inputs = {k: v.to(torch.float16) if v.dtype == torch.float32 else v
              for k, v in inputs.items()}

    # Run inference (no gradient tracking needed — saves memory)
    with torch.no_grad():
        logits = _model(**inputs).logits

    # Convert logits to probabilities using softmax
    probabilities = torch.nn.functional.softmax(logits, dim=-1)

    # Get label mapping from model config
    id2label = _model.config.id2label  # e.g., {0: "male", 1: "female"}

    scores = {}
    for idx, prob in enumerate(probabilities[0]):
        label = id2label[idx].lower()  # normalize to lowercase
        scores[label] = prob.item()

    female_prob = scores.get("female", 0.0)
    female_score = round(female_prob * 100, 2)

    logger.info(f"Voice scores — Female: {female_score:.1f}%, Male: {round((1-female_prob)*100, 2):.1f}%")
    return female_score


def _run_pipeline_sync(audio_bytes: bytes, face_verified: bool) -> dict:
    """
    Synchronous voice verification pipeline, executed in a thread pool
    to avoid blocking the FastAPI async event loop.

    Args:
        audio_bytes:   Raw WAV file bytes from multipart upload
        face_verified: Whether face verification already passed for this user

    Returns:
        Structured result dict with success, message, data fields
    """
    # Step 1: Load audio from bytes using soundfile
    try:
        audio_buffer = io.BytesIO(audio_bytes)
        audio_array, sample_rate = sf.read(audio_buffer, dtype='float32')
    except Exception as e:
        logger.error(f"Failed to read audio file: {e}")
        return {
            "success": False,
            "message": "Invalid audio format. Please send a valid WAV file (16kHz, Mono).",
        }

    # Minimum duration check (at least 2 seconds required for accuracy)
    duration_seconds = len(audio_array) / sample_rate
    if duration_seconds < 2.0:
        return {
            "success": False,
            "message": f"Audio too short ({duration_seconds:.1f}s). Minimum 2 seconds required for accurate analysis.",
        }

    # Step 2: Run gender classification model
    try:
        female_score = _get_female_score(audio_array, sample_rate)
    except Exception as e:
        logger.error(f"Voice model inference failed: {e}")
        return {
            "success": False,
            "message": f"AI Engine error: {str(e)}",
        }

    # Step 3: Apply scoring decision logic
    # ─────────────────────────────────────────────────────────────────────────
    # Score 80-100: Clearly female voice → Approve immediately
    # Score 50-79:  Ambiguous / deeper female voice → Approve ONLY if face
    #               verification is also True (two-factor fallback)
    # Score 0-49:   Likely male voice → Reject
    # ─────────────────────────────────────────────────────────────────────────

    if female_score >= FEMALE_CONFIRM_THRESHOLD:
        # Clear female voice
        return {
            "success": True,
            "message": "Voice verified successfully. Female voice confirmed.",
            "data": {
                "voice_score": female_score,
                "voice_verification": True
            }
        }

    elif female_score >= AMBIGUOUS_LOWER_THRESHOLD:
        # Ambiguous zone — check face verification as fallback
        if face_verified:
            return {
                "success": True,
                "message": "Voice Deep but face verification confirms identity.",
                "data": {
                    "voice_score": female_score,
                    "voice_verification": True
                }
            }
        else:
            return {
                "success": False,
                "message": "Voice score is Deep and face verification has not passed. Please complete face verification first.",
                "data": {
                    "voice_score": female_score,
                    "voice_verification": False
                }
            }

    else:
        # Score below 50 — reject
        return {
            "success": False,
            "message": "Male voice detected. SafeSpeak is for female users only.",
            "data": {
                "voice_score": female_score,
                "voice_verification": False
            }
        }


async def run_voice_pipeline(audio_file: UploadFile, face_verified: bool) -> dict:
    """
    Full async Voice Verification pipeline.
    Reads the uploaded WAV file and runs the AI pipeline in a thread pool
    so the FastAPI event loop is never blocked.

    Args:
        audio_file:    Uploaded WAV file from multipart form data
        face_verified: Whether the user has already passed face verification

    Returns:
        Structured result dict
    """
    # Read raw bytes from the uploaded file
    try:
        audio_bytes = await audio_file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded audio: {e}")
        return {
            "success": False,
            "message": "Failed to read uploaded audio file.",
        }

    # Run the heavy synchronous work in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _run_pipeline_sync,
        audio_bytes,
        face_verified
    )
