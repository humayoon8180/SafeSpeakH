#!/bin/bash
# SafeSpeak — Azure App Service Startup Script
# Starts both FastAPI (AI worker) and Django (API gateway)

echo "Starting SafeSpeak Deployment Script..."

ROOT_DIR=$(pwd)
echo "App running from: $ROOT_DIR"

# ── Step 1: Install Dependencies ─────────────────────────────────────────────
cd "$ROOT_DIR"
# NOTE: All dependencies (including PyTorch CPU and OpenCV headless) are now 
# strictly managed by Azure's Oryx build engine via requirements.txt.
# Runtime 'pip install' is disabled because Azure containers are read-only at runtime.

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