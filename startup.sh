#!/bin/bash
# SafeSpeak — Azure App Service Startup Script
# Starts both FastAPI (AI worker) and Django (API gateway)

echo "Starting SafeSpeak Deployment Script..."

ROOT_DIR=$(pwd)
echo "App running from: $ROOT_DIR"

# ── Step 1: Install Dependencies ─────────────────────────────────────────────
cd "$ROOT_DIR"
pip install --no-cache-dir -r requirements.txt

# ── Step 2: Start FastAPI AI worker in the background (internal only) ────────
cd "$ROOT_DIR/fastapi_app"
uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 &

# ── Step 3: Django Database & Static Files Setup ─────────────────────────────
cd "$ROOT_DIR/backend"
python manage.py migrate --no-input
python manage.py collectstatic --no-input

# ── Step 4: Start Django public server ───────────────────────────────────────
gunicorn --bind=0.0.0.0:8000 --timeout 600 core.wsgi