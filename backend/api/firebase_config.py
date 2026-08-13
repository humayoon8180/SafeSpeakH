import firebase_admin
from firebase_admin import credentials
from django.conf import settings
import os
import json

_firebase_app = None


def get_firebase_app():
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    # -----------------------------------------------------------
    # FIX 1 (thread-safety): if another request/thread already
    # initialized the default Firebase app while this one was
    # also on its way here, just grab the existing app instead
    # of calling initialize_app() again — that second call would
    # crash with "The default Firebase app already exists."
    # -----------------------------------------------------------
    try:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app
    except ValueError:
        pass  # not initialized yet — continue below

    firebase_env = os.environ.get('FIREBASE_CREDENTIALS_JSON')

    if firebase_env:
        # We are on Azure — load from the environment variable.
        cert_dict = json.loads(firebase_env)

        # -----------------------------------------------------------
        # FIX 2: defensive private_key newline normalization.
        # If Azure's Application Settings text box mangled the
        # multi-line private key when it was pasted in, this puts
        # the literal \n sequences back into real newlines so the
        # certificate parses correctly. This is a no-op (harmless)
        # if the value was already correct.
        # -----------------------------------------------------------
        if 'private_key' in cert_dict:
            cert_dict['private_key'] = cert_dict['private_key'].replace('\\n', '\n')

        cred = credentials.Certificate(cert_dict)
    else:
        # We are on localhost — load from the file on disk.
        cred_path = os.path.join(settings.BASE_DIR, 'firebase', 'firebase-credentials.json')
        if not os.path.exists(cred_path):
            raise ValueError("Firebase credentials missing! Not in Env Var and not in file.")
        cred = credentials.Certificate(cred_path)

    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app