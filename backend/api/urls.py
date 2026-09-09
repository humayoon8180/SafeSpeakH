# api/urls.py
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
    path('register/',             RegisterView.as_view(),          name='register'),
    path('login/',                LoginView.as_view(),              name='login'),
    path('profile/',              UserProfileView.as_view(),        name='profile'),
    path('verify-face/',          verify_face_gateway,              name='verify-face'),
    path('verify-voice/',         verify_voice_gateway,             name='verify-voice'),
    path('ping/',                 PingView.as_view(),               name='ping'),

    # ── Matchmaking & Calling ─────────────────────────────────────────────
    path('call/initiate/',        InitiateCallView.as_view(),       name='call-initiate'),
    path('set/fcm/',              SetFCMTokenView.as_view(),        name='set-fcm'),
    path('agora/generate-token/', GenerateAgoraTokenView.as_view(), name='generate_agora_token'),
    path('call/end/',             EndCallView.as_view(),            name='end_call'),
    path('call-feedback/',        SubmitCallDetailsView.as_view(),  name='submit-details'),
    path('history/',              UserFeedbackHistoryView.as_view(), name='user-feedback-history'),
    path('youtube-videos/',       YouTubeVideoView.as_view(),       name='youtube_videos'),
    path('terminate/',            TerminateAccountView.as_view(),   name='terminate'),
    path('appeal/',               AppealView.as_view(),             name='appeal'),
]