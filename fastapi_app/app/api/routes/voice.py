"""
api/routes/voice.py
FastAPI router for Voice Verification endpoint.

Endpoint:
  POST /verify/voice/
  - Accepts: multipart/form-data
      • audio_file (WAV file, 16kHz, Mono)
      • user_id    (int)
      • face_verified (bool, optional — defaults to False)
  - Returns: JSON with success, message, and score data
"""

import logging
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.services.voice_engine import run_voice_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/voice/")
async def verify_voice(
    audio_file: UploadFile = File(..., description="WAV audio file (16kHz, 16-bit, Mono)"),
    user_id: int = Form(..., description="User ID from the Django backend"),
    face_verified: bool = Form(False, description="Whether the user passed face verification"),
):
    """
    Voice Verification Endpoint.

    Accepts a WAV audio recording and determines if the speaker is female
    using the Wav2Vec2 gender recognition model.

    **Scoring Logic:**
    - Score 80-100 → ✅ Approved (clear female voice)
    - Score 50-79  → ⚠️ Approved only if face_verified=True
    - Score 0-49   → ❌ Rejected (male voice detected)

    **Audio Requirements:**
    - Format: WAV
    - Sample Rate: 16kHz
    - Channels: Mono
    - Minimum Duration: 3 seconds
    """
    logger.info(f"Voice verification request — user_id={user_id}, face_verified={face_verified}")

    result = await run_voice_pipeline(
        audio_file=audio_file,
        face_verified=face_verified
    )

    # Return 200 always — success/failure is communicated in the JSON body
    # (same pattern as face verification route)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(content=result, status_code=status_code)
