#!/bin/bash
# SafeSpeak — Azure App Service Startup Script
# Starts both FastAPI (AI worker, internal) and Django (public API gateway)

# ── Step 1: Install MSSQL ODBC Driver ───────────────────────────────────────
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update -y
ACCEPT_EULA=Y apt-get install -y msodbcsql17 -q

# ── Step 2: Start FastAPI AI worker in the background (internal only) ────────
cd /home/site/wwwroot/fastapi_app
# Binds to 127.0.0.1 — not reachable from internet, only Django can call it
uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 &

# ── Step 3: Django setup ─────────────────────────────────────────────────────
cd /home/site/wwwroot/backend
python manage.py migrate --no-input
python manage.py collectstatic --no-input

# ── Step 6: Start Django public server ───────────────────────────────────────
gunicorn --bind=0.0.0.0:8000 --timeout 600 core.wsgi