# api/models.py
# UserProfile model with verification fields

from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    user               = models.OneToOneField(User, on_delete=models.CASCADE)
    face_verification  = models.BooleanField(default=False)
    voice_verification = models.BooleanField(default=False)
    voice_score        = models.FloatField(default=0.0)
    
    # --- New Profile Fields ---
    total_calls        = models.IntegerField(default=0)
    profile_image_url  = models.URLField(max_length=1000, blank=True, null=True)
    rating             = models.FloatField(default=0.0)
    proficiency_level  = models.CharField(max_length=100, blank=True, null=True)
    reports            = models.IntegerField(default=0)
    country            = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.email}"