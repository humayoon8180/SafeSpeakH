"""
api/routes/face.py
Face Verification & Gender Check endpoint.

Endpoint : POST /verify/face/
Input    : Multipart Form — live_image
Output   : JSON with face detection and gender status
"""

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from app.services.face_engine import run_face_pipeline

router = APIRouter()

@router.post("/face/")
async def verify_face(
    live_image: UploadFile = File(..., description="Live capture frame")
) -> JSONResponse:
    """
    POST /verify/face/

    Accepts 1 image as Multipart Form Data:
      - live_image: The selfie uploaded by the user.

    Returns structured JSON based on face detection and gender check.
    """

    # ── Run the AI pipeline ─────────────────────────────────────────────────
    try:
        # We pass the UploadFile directly; reading and compression is handled in the engine.
        result = await run_face_pipeline(live_image)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI pipeline error: {str(e)}")

    # ── Build response ───────────────────────────────────────────────────────
    # Always return 200 — let the frontend read the status from the JSON body.
    # 500 is reserved for server crashes, 400 for bad input.
    return JSONResponse(
        status_code=200,
        content=result
    )
