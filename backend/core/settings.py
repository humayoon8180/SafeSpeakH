# =============================================================================
# core/settings.py
# Production configuration for the SafeSpeak Django application.
#
# Environment variables are loaded from a .env file (local development) or
# from Azure App Service Application Settings (production). All secrets must
# be provided via environment variables — no credentials are hardcoded.
# =============================================================================

import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Secret key must be overridden via the SECRET_KEY environment variable in
# all deployed environments. The fallback value is intentionally weak and
# must never be used in production.
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
DEBUG = False

# Allow requests from the Azure App Service domain and local development hosts.
ALLOWED_HOSTS = [
    '.azurewebsites.net',
    'localhost',
    '127.0.0.1',
]

# Trust HTTPS origins for CSRF validation on the Azure deployment domain.
CSRF_TRUSTED_ORIGINS = [
    'https://*.azurewebsites.net'
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'api.apps.ApiConfig',
]

# CorsMiddleware must be positioned before SecurityMiddleware and all other
# middleware to ensure CORS preflight (OPTIONS) requests are handled before
# any authentication or CSRF checks can reject them.
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Primary database: Azure SQL Server accessed via the MSSQL Django backend
# and ODBC Driver 17. All connection parameters are injected from environment
# variables; the ODBC driver is installed at container startup via startup.sh.
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME':     os.getenv('DB_NAME'),
        'USER':     os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST':     os.getenv('DB_HOST'),
        'PORT':     '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'extra_params': 'Encrypt=yes;TrustServerCertificate=no;'
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalisation
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Karachi'
USE_I18N      = True
USE_TZ        = True

# Static file serving via WhiteNoise with content-hash-based cache busting.
STATIC_URL          = '/static/'
STATIC_ROOT         = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Allow cross-origin requests from all origins to support the Flutter mobile
# client. Restrict this to specific origins in higher-security deployments.
CORS_ALLOW_ALL_ORIGINS = True

# REST Framework — JWT Bearer token authentication as the default scheme.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

# JWT token lifetime configuration.
# 30-day access and refresh tokens are appropriate for a mobile application
# where forced re-authentication is a poor user experience.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Point Django's authentication machinery at the custom User model.
AUTH_USER_MODEL = 'api.User'
