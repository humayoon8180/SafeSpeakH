"""
services/face_engine.py
Core AI engine for Face Verification and Gender Check.

Pipeline:
  Step 1 — Read image bytes and decompress using Pillow.
  Step 2 — Smart Compression: Resize if width > 1024px to save memory.
  Step 3 — DeepFace.analyze: Detect face and confirm gender is Female.
  Step 4 — Return structured JSON result.
"""

import os

# Set DeepFace home directory to the project folder (F: drive) to save C: drive space
# Must be set BEFORE importing deepface
os.environ["DEEPFACE_HOME"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

import io
import asyncio
import logging
import cv2
import numpy as np
from PIL import Image
from fastapi import UploadFile
from deepface import DeepFace

logger = logging.getLogger(__name__)


def preload_models() -> None:
    """
    Called once at FastAPI startup via lifespan.
    Warms up DeepFace models by running a dummy image.
    No mediapipe imports or logic here.
    """
    logger.info("Warming up DeepFace gender model...")
    try:
        dummy = np.zeros((224, 224, 3), dtype=np.uint8)
        DeepFace.analyze(
            img_path=dummy,
            actions=["gender"],
            detector_backend="skip",
            enforce_detection=False,
            silent=True
        )
        logger.info("DeepFace gender model ready.")
    except Exception as e:
        logger.warning(f"DeepFace warm-up skipped: {e}")


def _compress_and_convert(image_bytes: bytes) -> np.ndarray:
    """
    Reads image bytes, applies smart compression if width > 1024,
    and returns an RGB numpy array converted to BGR for DeepFace/OpenCV.
    """
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # ── Smart Compression (Resize > 1024px) ──────────────────────────────
    MAX_DIMENSION = 1024
    width, height = pil_img.size
    
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        # thumbnail modifies in-place, preserves aspect ratio
        pil_img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
        logger.info(f"Auto-compressed image from {width}x{height} to {pil_img.width}x{pil_img.height}")
        
    # Convert to BGR format which OpenCV and DeepFace backend expect
    bgr_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return bgr_img


async def run_face_pipeline(image_file: UploadFile) -> dict:
    """
    Full async Face Verification pipeline for a single image.
    """
    try:
        image_bytes = await image_file.read()
    except Exception as e:
        logger.error(f"Failed to read upload file: {e}")
        return {
            "status": "rejected",
            "face_detected": False,
            "reason": "Failed to read uploaded image."
        }
        
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _run_pipeline_sync,
        image_bytes
    )


def _run_pipeline_sync(image_bytes: bytes) -> dict:
    """Synchronous pipeline executed in a thread pool."""
    try:
        # Step 1 & 2: Decode and compress
        img_bgr = _compress_and_convert(image_bytes)
    except Exception as e:
        logger.error(f"Image decode/compress failed: {e}")
        return {
            "status": "rejected",
            "face_detected": False,
            "reason": "Invalid image format or corrupted file."
        }

    # Step 3 & 4: Analyze with DeepFace
    try:
        analysis = DeepFace.analyze(
            img_path=img_bgr,
            actions=["gender"],
            detector_backend="retinaface",
            enforce_detection=True,
            silent=True
        )
        
        # DeepFace returns a list of faces if multiple are found
        if isinstance(analysis, list):
            analysis = analysis[0]
            
        dominant_gender = analysis.get("dominant_gender", "Unknown")
        gender_scores = analysis.get("gender", {})
        gender_confidence = round(float(gender_scores.get(dominant_gender, 0.0)), 2)
        is_female = dominant_gender == "Woman"
        
        if is_female:
            return {
                "status": "approved",
                "face_detected": True,
                "gender": dominant_gender,
                "gender_confidence": gender_confidence,
                "is_female": True
            }
        else:
            return {
                "status": "rejected",
                "face_detected": True,
                "gender": dominant_gender,
                "gender_confidence": gender_confidence,
                "is_female": False,
                "reason": "Male face detected. SafeSpeak is female-only."
            }

    except ValueError:
        # ValueError is raised by DeepFace when enforce_detection=True and no face is found
        return {
            "status": "rejected",
            "face_detected": False,
            "reason": "No human face detected in the image."
        }
    except Exception as e:
        logger.error(f"DeepFace analysis failed: {e}")
        return {
            "status": "rejected",
            "face_detected": False,
            "reason": f"AI Engine error: {str(e)}"
        }
