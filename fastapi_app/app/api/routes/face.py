"""
api/routes/face.py
Face Verification & Liveness Detection endpoint.

Endpoint : POST /verify/face/
Input    : Multipart Form — profile_image + frame_1 + frame_2 + frame_3
Output   : JSON with liveness, face match, gender, and final decision
"""

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from app.services.face_engine import run_face_pipeline

router = APIRouter()


@router.post("/face/")
async def verify_face(
    profile_image: UploadFile = File(..., description="User's stored profile photo"),
    frame_1: UploadFile       = File(..., description="Live capture frame 1 (blink start)"),
    frame_2: UploadFile       = File(..., description="Live capture frame 2 (head left)"),
    frame_3: UploadFile       = File(..., description="Live capture frame 3 (head right)"),
) -> JSONResponse:
    """
    POST /verify/face/

    Accepts 4 images as Multipart Form Data:
      - profile_image : The stored profile photo to verify against
      - frame_1       : Live frame 1
      - frame_2       : Live frame 2
      - frame_3       : Live frame 3

    Pipeline (inside face_engine.py):
      1. Decode all 4 images
      2. Run MediaPipe liveness on all 3 live frames
      3. Select sharpest live frame
      4. DeepFace ArcFace — compare best frame vs profile_image
      5. DeepFace analyze  — confirm gender is Female

    Returns a unified JSON with overall_approved: true/false.
    """

    # ── Validate MIME types ─────────────────────────────────────────────────
    ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    files = {
        "profile_image": profile_image,
        "frame_1"      : frame_1,
        "frame_2"      : frame_2,
        "frame_3"      : frame_3,
    }

    for field_name, upload_file in files.items():
        if upload_file.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"'{field_name}' must be a JPEG, PNG, or WebP image. "
                       f"Received: {upload_file.content_type}"
            )

    # ── Read raw bytes from all uploads ─────────────────────────────────────
    try:
        profile_bytes = await profile_image.read()
        frame1_bytes  = await frame_1.read()
        frame2_bytes  = await frame_2.read()
        frame3_bytes  = await frame_3.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded files: {str(e)}")

    # ── Validate file sizes (max 5MB per image) ──────────────────────────────
    MAX_SIZE = 5 * 1024 * 1024  # 5MB
    size_checks = {
        "profile_image": profile_bytes,
        "frame_1"      : frame1_bytes,
        "frame_2"      : frame2_bytes,
        "frame_3"      : frame3_bytes,
    }
    for field_name, raw_bytes in size_checks.items():
        if len(raw_bytes) > MAX_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"'{field_name}' exceeds 5MB limit."
            )

    # ── Run the AI pipeline ─────────────────────────────────────────────────
    try:
        result = await run_face_pipeline(
            profile_image_bytes = profile_bytes,
            frame1_bytes        = frame1_bytes,
            frame2_bytes        = frame2_bytes,
            frame3_bytes        = frame3_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI pipeline error: {str(e)}")

    # ── Build response ───────────────────────────────────────────────────────
    http_status = 200 if result["overall_approved"] else 200
    # Always return 200 — let Flutter read overall_approved: true/false
    # 500 is reserved for server errors only

    return JSONResponse(
        status_code=http_status,
        content={
            "status"           : "success" if result["overall_approved"] else "rejected",
            "overall_approved" : result["overall_approved"],
            "liveness": {
                "passed" : result["liveness_passed"],
                "detail" : result["liveness_detail"],
            },
            "face_match": {
                "verified" : result["verified"],
                "distance" : result["distance"],
                "threshold": result["threshold"],
            },
            "gender": {
                "detected"   : result["gender"],
                "confidence" : result["gender_confidence"],
                "passed"     : result["gender_passed"],
            },
            "rejection_reason": result["rejection_reason"],
        }
    )
