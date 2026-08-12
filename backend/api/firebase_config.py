import firebase_admin
from firebase_admin import credentials
from django.conf import settings
import os

_firebase_app = None

def get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        cred_path = os.path.join(settings.BASE_DIR, 'firebase', 'firebase-credentials.json')
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app