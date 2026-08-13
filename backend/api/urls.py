# api/urls.py
from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    UserProfileView,
    verify_face_gateway,
    PingView,
    InitiateCallView,
    SetFCMTokenView
)

urlpatterns = [
    path('register/',        RegisterView.as_view(),          name='register'),
    path('login/',           LoginView.as_view(),              name='login'),
    path('profile/',         UserProfileView.as_view(),        name='profile'),
    path('verify-face/',     verify_face_gateway,              name='verify-face'),
    path('ping/',            PingView.as_view(),               name='ping'),

    # ── Matchmaking & Calling ─────────────────────────────────────────────────
    # NEW: Atomic find + lock + notify (recommended, fixes race condition)
    path('call/initiate/',   InitiateCallView.as_view(),       name='call-initiate'),
    path('set/fcm/', SetFCMTokenView.as_view(), name='set-fcm'),
]