#!/bin/bash
# Install MSSQL ODBC Driver
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update -y
ACCEPT_EULA=Y apt-get install -y msodbcsql17 -q

# Backend folder mein jao — manage.py yahan hai
cd /home/site/wwwroot/backend

# Requirements install karo
pip install -r requirements.txt

# Django migrate
python manage.py migrate --no-input

# Static files
python manage.py collectstatic --no-input

# Server start
gunicorn --bind=0.0.0.0:8000 --timeout 600 core.wsgi