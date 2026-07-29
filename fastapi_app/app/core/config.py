"""
core/config.py
Application settings loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Server
    APP_TITLE: str = "SafeSpeak AI Microservice"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS — Django backend + Flutter dev origins
    ALLOWED_ORIGINS: list = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://10.0.2.2:8000",  # Android emulator → host machine
        "*",                      # Allow all for FYP stage
    ]

    # Face verification thresholds
    FACE_GENDER_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("FACE_GENDER_CONFIDENCE_THRESHOLD", "60.0")
    )
    FACE_VERIFY_DISTANCE_THRESHOLD: float = float(
        os.getenv("FACE_VERIFY_DISTANCE_THRESHOLD", "0.68")  # ArcFace default
    )

    # Liveness thresholds
    LIVENESS_MIN_LANDMARKS: int = int(
        os.getenv("LIVENESS_MIN_LANDMARKS", "200")
    )


# Single instance used across the app
settings = Settings()
