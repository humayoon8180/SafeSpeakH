"""
main.py
FastAPI application entry point.
Models are preloaded at startup to eliminate cold-start delay.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api.routes import face, voice


# ── Startup / Shutdown lifecycle ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Preload all heavy AI models once at server startup.
    This eliminates the 8-15 second cold-start on the first request.
    """
    print("[SafeSpeak AI] Preloading AI models — please wait...")
    from app.services.face_engine import preload_models as preload_face
    from app.services.voice_engine import preload_models as preload_voice
    from app.services.ecapa_engine import preload_ecapa
    preload_face()
    preload_voice()
    preload_ecapa()
    print("[SafeSpeak AI] All models loaded. Server ready.")
    yield
    # Shutdown cleanup (if needed in future)
    print("[SafeSpeak AI] Shutting down.")


# ── App instance ────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS Middleware ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Restrict to specific origins in production
    allow_credentials=False,   # Must be False when allow_origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(face.router,  prefix="/verify", tags=["Face Verification"])
app.include_router(voice.router, prefix="/verify", tags=["Voice Verification"])


# ── Health check ────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status": "online",
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
    }
