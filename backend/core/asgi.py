"""
core/asgi.py — Standard Django ASGI configuration.
WebSockets have been removed. This project now uses HTTP Ping/Heartbeat
for presence tracking and Firebase FCM for push notifications.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_asgi_application()
