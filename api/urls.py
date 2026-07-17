# URLs for API app

from django.urls import path
from .views import RegisterView, LoginView, UserProfileView

# Yahan hum apne views ko specific raaston (endpoints) se link kar rahe hain
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('profile/', UserProfileView.as_view(), name='profile'),
]