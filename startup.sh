#!/bin/bash

# Install ODBC Driver 17 for SQL Server
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update -y
ACCEPT_EULA=Y apt-get install -y msodbcsql17

# Move to backend directory
cd /home/site/wwwroot/backend

# Run Django commands
python manage.py migrate --no-input
python manage.py collectstatic --no-input

# Start gunicorn
gunicorn --bind=0.0.0.0:8000 --timeout 600 core.wsgi