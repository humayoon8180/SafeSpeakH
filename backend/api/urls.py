# api/urls.py
from django.urls import path
from .views import RegisterView, LoginView, UserProfileView, verify_face_gateway

urlpatterns = [
    path('register/',    RegisterView.as_view(),   name='register'),
    path('login/',       LoginView.as_view(),       name='login'),
    path('profile/',     UserProfileView.as_view(), name='profile'),
    path('verify-face/', verify_face_gateway,       name='verify-face'),
]