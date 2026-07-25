# api/models.py
# UserProfile model with verification fields

from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    user               = models.OneToOneField(User, on_delete=models.CASCADE)
    face_verification  = models.BooleanField(default=False)
    voice_verification = models.BooleanField(default=False)
    voice_score        = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.user.email}"