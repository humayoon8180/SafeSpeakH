"""
services/face_engine.py
Core AI engine for Face Verification and Gender Check.

ALL heavy imports (cv2, numpy, PIL, DeepFace/TensorFlow) are inside functions.
At uvicorn startup, this module imports ONLY: os, io, asyncio, logging.
This prevents the TF + PyTorch dual-import RAM spike that was OOM-killing FastAPI on Azure B2.
"""

import os
import io
import asyncio
import logging

# Set DeepFace model storage directory BEFORE any deepface import.
if not os.environ.get("DEEPFACE_HOME"):
    os.environ["DEEPFACE_HOME"] = os.path.join(os.getcwd(), ".deepface_models")

# Force TF to CPU only and suppress verbose CUDA logs
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

logger = logging.getLogger(__name__)


def preload_models() -> None:
    """
    Called at FastAPI startup. Kept as a no-op intentionally.
    All heavy libraries load lazily on the first API request.
    """
    logger.info("Face engine ready. All imports are lazy — startup RAM is minimal.")


def _compress_and_convert(image_bytes: bytes):
    """
    Reads image bytes, applies smart compression if width > 1024,
    and returns an RGB numpy array converted to BGR for DeepFace/OpenCV.
    All imports are inside this function (lazy).
    """
    import cv2
    import numpy as np
    from PIL import Image

    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    MAX_DIMENSION = 1024
    width, height = pil_img.size
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        pil_img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
        logger.info(f"Auto-compressed image from {width}x{height} to {pil_img.width}x{pil_img.height}")

    bgr_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return bgr_img


async def run_face_pipeline(image_file) -> dict:
    """Full async Face Verification pipeline for a single image."""
    try:
        image_bytes = await image_file.read()
    except Exception as e:
        logger.error(f"Failed to read upload file: {e}")
        return {"success": False, "message": "Failed to read uploaded image."}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_pipeline_sync, image_bytes)


def _run_pipeline_sync(image_bytes: bytes) -> dict:
    """Synchronous pipeline executed in a thread pool. All heavy imports are here."""

    # ── Lazy imports: TF/DeepFace only loads on first request, NOT at startup ──
    from deepface import DeepFace

    try:
        img_bgr = _compress_and_convert(image_bytes)
    except Exception as e:
        logger.error(f"Image decode/compress failed: {e}")
        return {"success": False, "message": "Invalid image format or corrupted file."}

    try:
        analysis = DeepFace.analyze(
            img_path=img_bgr,
            actions=["gender"],
            detector_backend="retinaface",
            enforce_detection=True,
            silent=True
        )

        if isinstance(analysis, list):
            analysis = analysis[0]

        dominant_gender = analysis.get("dominant_gender", "Unknown")
        gender_scores   = analysis.get("gender", {})
        gender_confidence = round(float(gender_scores.get(dominant_gender, 0.0)), 2)
        is_female = dominant_gender == "Woman"

        if is_female:
            return {
                "success": True,
                "message": "Face verified successfully.",
                "data": {
                    "face_detected": True,
                    "gender": dominant_gender,
                    "gender_confidence": gender_confidence,
                    "face_verification": True
                }
            }
        else:
            return {
                "success": False,
                "message": "Male face detected. SafeSpeak is female-only.",
                "data": {
                    "face_detected": True,
                    "gender": dominant_gender,
                    "gender_confidence": gender_confidence,
                    "face_verification": False
                }
            }

    except ValueError:
        return {"success": False, "message": "No human face detected in the image."}
    except Exception as e:
        logger.error(f"DeepFace analysis failed: {e}")
        return {"success": False, "message": f"AI Engine error: {str(e)}"}
