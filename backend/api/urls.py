# =============================================================================
# api/urls.py
# URL Route Declarations for the SafeSpeak REST API.
#
# Route Categorization:
#   - Identity & Account Management  : /register/, /login/, /profile/, /terminate/, /appeal/
#   - Biometric Verification Gateways: /verify-face/, /verify-voice/
#   - Presence & Push Notifications  : /ping/, /set/fcm/
#   - Real-Time Calling & Signaling  : /call/initiate/, /agora/generate-token/, /call/end/
#   - Call Feedback & History        : /call-feedback/, /history/
#   - Educational Content Feed       : /youtube-videos/
# =============================================================================

from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    UserProfileView,
    verify_face_gateway,
    verify_voice_gateway,
    PingView,
    InitiateCallView,
    SetFCMTokenView,
    GenerateAgoraTokenView,
    EndCallView,
    SubmitCallDetailsView,
    UserFeedbackHistoryView,
    YouTubeVideoView,
    TerminateAccountView,
    AppealView,
)

urlpatterns = [
    # ── Identity & Account Management ─────────────────────────────────────────
    path('register/',             RegisterView.as_view(),          name='register'),
    path('login/',                LoginView.as_view(),              name='login'),
    path('profile/',              UserProfileView.as_view(),        name='profile'),
    path('terminate/',            TerminateAccountView.as_view(),   name='terminate'),
    path('appeal/',               AppealView.as_view(),             name='appeal'),

    # ── Biometric Verification Gateways (FastAPI Proxy) ──────────────────────
    path('verify-face/',          verify_face_gateway,              name='verify-face'),
    path('verify-voice/',         verify_voice_gateway,             name='verify-voice'),

    # ── Presence & Push Notifications ─────────────────────────────────────────
    path('ping/',                 PingView.as_view(),               name='ping'),
    path('set/fcm/',              SetFCMTokenView.as_view(),        name='set-fcm'),

    # ── Real-Time Matchmaking & Calling ───────────────────────────────────────
    path('call/initiate/',        InitiateCallView.as_view(),       name='call-initiate'),
    path('agora/generate-token/', GenerateAgoraTokenView.as_view(), name='generate_agora_token'),
    path('call/end/',             EndCallView.as_view(),            name='end_call'),

    # ── Feedback & Analytics ──────────────────────────────────────────────────
    path('call-feedback/',        SubmitCallDetailsView.as_view(),  name='submit-details'),
    path('history/',              UserFeedbackHistoryView.as_view(), name='user-feedback-history'),

    # ── Educational Resources ─────────────────────────────────────────────────
    path('youtube-videos/',       YouTubeVideoView.as_view(),       name='youtube_videos'),
]