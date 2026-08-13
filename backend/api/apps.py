import threading
import time
import os
import sys
from django.apps import AppConfig
from django.utils import timezone
from datetime import timedelta


def run_ghost_cleanup():
    """
    Background thread that runs continuously.
    It cleans up ghost users every 15 seconds.
    """
    from .models import UserActiva

    while True:
        try:
            cutoff_time = timezone.now() - timedelta(seconds=20)

            ghost_users = UserActiva.objects.filter(
                is_active=True,
                last_ping_time__lt=cutoff_time
            )

            count = ghost_users.count()
            if count > 0:
                ghost_users.update(is_active=False, is_on_call=False)
                print(f"[Auto-Cleanup] {count} user(s) did not ping recently. Marked as Inactive in DB.", flush=True)

        except Exception as e:
            print(f"[Auto-Cleanup] Error: {e}", flush=True)

        time.sleep(15)


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        is_gunicorn = bool(sys.argv) and 'gunicorn' in sys.argv[0]
        is_runserver_main = 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true'

        if is_gunicorn or is_runserver_main:
            print("[Auto-Cleanup] Background thread started. Monitoring for inactive users...", flush=True)
            thread = threading.Thread(target=run_ghost_cleanup, daemon=True)
            thread.start()