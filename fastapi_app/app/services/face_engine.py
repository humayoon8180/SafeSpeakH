"""
services/face_engine.py
Core AI engine for Face Verification and Liveness Detection.

Pipeline:
  Step 1 — MediaPipe: Check all 3 live frames for real facial landmarks (liveness)
  Step 2 — Frame selection: Pick the sharpest/best frame from the 3
  Step 3 — DeepFace verify: Compare best live frame against profile image (ArcFace)
  Step 4 — DeepFace analyze: Confirm gender is Female
  Step 5 — Return unified result dict
"""

import io
import asyncio
import logging
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# ── Global model references (loaded once at startup) ────────────────────────
_face_mesh = None          # MediaPipe FaceMesh instance
_mp_drawing = None         # MediaPipe drawing utils (unused in prod, kept for debug)
_mp_face_mesh = None       # MediaPipe face_mesh module reference


def preload_models() -> None:
    """
    Called once at FastAPI startup via lifespan.
    Loads MediaPipe FaceMesh into memory.
    DeepFace loads its ArcFace model lazily on first call — acceptable
    because the first real request triggers it (not a user-facing request).
    """
    global _face_mesh, _mp_drawing, _mp_face_mesh

    logger.info("Loading MediaPipe FaceMesh...")
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh
    _mp_drawing   = mp.solutions.drawing_utils
    _face_mesh    = _mp_face_mesh.FaceMesh(
        static_image_mode=True,     # Each image processed independently
        max_num_faces=1,            # Only detect one face per frame
        refine_landmarks=True,      # Enables iris landmarks (468 → 478 points)
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    logger.info("MediaPipe FaceMesh loaded successfully.")


# ── Internal helpers ────────────────────────────────────────────────────────

def _bytes_to_bgr(image_bytes: bytes) -> Optional[np.ndarray]:
    """Convert raw image bytes to a BGR numpy array (OpenCV format)."""
    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return bgr
    except Exception as e:
        logger.error(f"Image decode failed: {e}")
        return None


def _compute_sharpness(bgr_image: np.ndarray) -> float:
    """
    Laplacian variance — higher value means sharper/clearer image.
    Used to select the best frame from the 3 live captures.
    """
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _check_single_frame_liveness(bgr_image: np.ndarray) -> dict:
    """
    Run MediaPipe FaceMesh on a single frame.
    Returns:
      is_live       : bool — face landmarks detected above threshold
      landmark_count: int  — number of landmarks found
    """
    if _face_mesh is None:
        raise RuntimeError("MediaPipe FaceMesh is not loaded. Call preload_models() first.")

    rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    result = _face_mesh.process(rgb)

    if not result.multi_face_landmarks:
        return {"is_live": False, "landmark_count": 0}

    # refine_landmarks=True gives 478 landmarks
    landmark_count = len(result.multi_face_landmarks[0].landmark)
    is_live = landmark_count >= 200  # Threshold: at least 200 of 478 landmarks

    return {"is_live": is_live, "landmark_count": landmark_count}


# ── Public async API ────────────────────────────────────────────────────────

async def run_face_pipeline(
    profile_image_bytes: bytes,
    frame1_bytes: bytes,
    frame2_bytes: bytes,
    frame3_bytes: bytes,
) -> dict:
    """
    Full async Face Verification + Liveness pipeline.

    Args:
        profile_image_bytes : The user's stored profile photo (reference).
        frame1_bytes        : Live frame 1 (e.g. blink start).
        frame2_bytes        : Live frame 2 (e.g. head left).
        frame3_bytes        : Live frame 3 (e.g. head right).

    Returns a unified dict:
        {
            "liveness_passed"   : bool,
            "liveness_detail"   : {frame results},
            "verified"          : bool,   # face match result
            "distance"          : float,  # ArcFace distance (lower = more similar)
            "threshold"         : float,  # ArcFace threshold for this model
            "gender"            : str,    # "Woman" or "Man"
            "gender_confidence" : float,  # 0–100
            "gender_passed"     : bool,   # True if gender == "Woman"
            "overall_approved"  : bool,   # True only if all 3 checks pass
            "rejection_reason"  : str | None
        }
    """
    # Run in thread pool — CPU-bound operations should not block async event loop
    return await asyncio.get_event_loop().run_in_executor(
        None, _run_pipeline_sync,
        profile_image_bytes, frame1_bytes, frame2_bytes, frame3_bytes
    )


def _run_pipeline_sync(
    profile_image_bytes: bytes,
    frame1_bytes: bytes,
    frame2_bytes: bytes,
    frame3_bytes: bytes,
) -> dict:
    """
    Synchronous implementation of the full pipeline.
    Called via run_in_executor to avoid blocking the event loop.
    """
    import deepface.DeepFace as DeepFace

    # ── Step 1: Decode all images ───────────────────────────────────────────
    frames_bytes = [frame1_bytes, frame2_bytes, frame3_bytes]
    frames_bgr   = []
    for i, fb in enumerate(frames_bytes):
        img = _bytes_to_bgr(fb)
        if img is None:
            return _rejection(f"Frame {i+1} could not be decoded.")
        frames_bgr.append(img)

    profile_bgr = _bytes_to_bgr(profile_image_bytes)
    if profile_bgr is None:
        return _rejection("Profile image could not be decoded.")

    # ── Step 2: Liveness check on all 3 frames ──────────────────────────────
    liveness_results = {}
    live_frames      = []

    for i, frame in enumerate(frames_bgr):
        result = _check_single_frame_liveness(frame)
        liveness_results[f"frame_{i+1}"] = result
        if result["is_live"]:
            live_frames.append((frame, _compute_sharpness(frame)))

    # Liveness passes if at least 2 of 3 frames contain real face landmarks
    liveness_passed = len(live_frames) >= 2

    if not liveness_passed:
        return {
            "liveness_passed"  : False,
            "liveness_detail"  : liveness_results,
            "verified"         : False,
            "distance"         : None,
            "threshold"        : None,
            "gender"           : None,
            "gender_confidence": None,
            "gender_passed"    : False,
            "overall_approved" : False,
            "rejection_reason" : "Liveness check failed — real face not detected in enough frames.",
        }

    # ── Step 3: Select best live frame (highest sharpness score) ────────────
    best_frame_bgr = max(live_frames, key=lambda x: x[1])[0]

    # Convert best frame to RGB PIL Image for DeepFace (DeepFace accepts numpy)
    best_frame_rgb = cv2.cvtColor(best_frame_bgr, cv2.COLOR_BGR2RGB)
    profile_rgb    = cv2.cvtColor(profile_bgr,    cv2.COLOR_BGR2RGB)

    # ── Step 4: DeepFace verification (ArcFace — face match) ────────────────
    try:
        verify_result = DeepFace.verify(
            img1_path      = best_frame_rgb,
            img2_path      = profile_rgb,
            model_name     = "ArcFace",
            detector_backend = "opencv",   # Fast detector — faces already cropped
            enforce_detection = False,     # Don't crash if face not re-detected
        )
        is_verified = verify_result.get("verified", False)
        distance    = round(verify_result.get("distance", 1.0), 4)
        threshold   = round(verify_result.get("threshold", 0.68), 4)

    except Exception as e:
        logger.error(f"DeepFace.verify failed: {e}")
        return _rejection(f"Face verification engine error: {str(e)}")

    # ── Step 5: DeepFace gender analysis ────────────────────────────────────
    try:
        analysis = DeepFace.analyze(
            img_path         = best_frame_rgb,
            actions          = ["gender"],
            detector_backend = "opencv",
            enforce_detection = False,
            silent           = True,
        )
        # analyze() returns a list when multiple faces found — take first
        if isinstance(analysis, list):
            analysis = analysis[0]

        gender_scores     = analysis.get("gender", {})
        dominant_gender   = analysis.get("dominant_gender", "Unknown")
        # DeepFace returns "Woman" and "Man" keys in gender dict
        gender_confidence = round(gender_scores.get(dominant_gender, 0.0), 2)
        gender_passed     = dominant_gender == "Woman"

    except Exception as e:
        logger.error(f"DeepFace.analyze failed: {e}")
        return _rejection(f"Gender analysis engine error: {str(e)}")

    # ── Step 6: Final decision ───────────────────────────────────────────────
    overall_approved = liveness_passed and is_verified and gender_passed
    rejection_reason = None

    if not is_verified:
        rejection_reason = "Face does not match profile image."
    elif not gender_passed:
        rejection_reason = f"Gender verification failed — detected: {dominant_gender}."

    return {
        "liveness_passed"  : liveness_passed,
        "liveness_detail"  : liveness_results,
        "verified"         : is_verified,
        "distance"         : distance,
        "threshold"        : threshold,
        "gender"           : dominant_gender,
        "gender_confidence": gender_confidence,
        "gender_passed"    : gender_passed,
        "overall_approved" : overall_approved,
        "rejection_reason" : rejection_reason,
    }


def _rejection(reason: str) -> dict:
    """Helper to build a consistent rejection response."""
    return {
        "liveness_passed"  : False,
        "liveness_detail"  : {},
        "verified"         : False,
        "distance"         : None,
        "threshold"        : None,
        "gender"           : None,
        "gender_confidence": None,
        "gender_passed"    : False,
        "overall_approved" : False,
        "rejection_reason" : reason,
    }
