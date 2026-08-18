#!/bin/bash
# SafeSpeak — Azure App Service Startup Script
# Starts both FastAPI (AI worker) and Django (API gateway)

echo "Starting SafeSpeak Deployment Script..."

ROOT_DIR=$(pwd)
echo "App running from: $ROOT_DIR"

# ── Step 1: Install Dependencies ─────────────────────────────────────────────
cd "$ROOT_DIR"
# Install CPU-only PyTorch FIRST (Azure B2 has no GPU — avoids 2GB CUDA download)
pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
# Install all other dependencies
pip install --no-cache-dir -r requirements.txt
# Remove GUI OpenCV — requires libxcb.so.1 (X11 display) which doesn't exist on Azure Linux
pip uninstall -y opencv-python opencv-contrib-python 2>/dev/null || true
# Use stable OpenCV 4.8.1.78 — v5.0 beta breaks DeepFace (copyMakeBorder missing)
pip install opencv-python-headless==4.8.1.78 --quiet

# ── Step 2: Start FastAPI AI worker in the background (internal only) ────────
cd "$ROOT_DIR/fastapi_app"
# Log FastAPI output to a file so Azure log stream shows any crashes
uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 >> /tmp/fastapi.log 2>&1 &
echo "FastAPI started in background (port 8001). Logs: /tmp/fastapi.log"

# Wait 5 seconds to give FastAPI time to boot before Django starts accepting requests
sleep 5

# ── Step 3: Django Database & Static Files Setup ─────────────────────────────
cd "$ROOT_DIR/backend"
python manage.py migrate --no-input
python manage.py collectstatic --no-input

# ── Step 4: Start Django public server (WSGI via Gunicorn) ────────────────────
gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 2 core.wsgi