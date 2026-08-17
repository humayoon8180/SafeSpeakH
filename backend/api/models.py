# api/models.py
# UserProfile model with verification fields

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class User(AbstractUser):
    face_verification = models.BooleanField(default=False)
    voice_verification = models.BooleanField(default=False)
    voice_score = models.FloatField(default=0.0)
    
    # Custom profile fields
    country = models.CharField(max_length=100, blank=True, null=True)
    proficiency_level = models.CharField(max_length=100, blank=True, null=True)
    profile_image_url = models.URLField(max_length=1000, blank=True, null=True)
    rating = models.FloatField(default=0.0)
    reports = models.IntegerField(default=0)
    total_calls = models.IntegerField(default=0)

    class Meta:
        db_table = 'auth_user'  # Uses existing auth_user table

    def __str__(self):
        return self.email or self.username

# api/models.py mein add karo

class UserActiva(models.Model):
    # One to one with Django User
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='activa',
        primary_key=True
    )
    # Firebase token for notifications
    fcm_token = models.CharField(
        max_length=500, 
        blank=True, 
        default=''
    )
    # Is app open/foreground (set by ping, cleared by auto-cleanup)
    is_active = models.BooleanField(default=False)
    
    # Is user on call
    is_on_call = models.BooleanField(default=False)

    # Timestamp when the call lock was set — used for stale-lock auto-release.
    # If is_on_call=True but call_locked_at is >15s ago, the lock is stale and ignored.
    call_locked_at = models.DateTimeField(null=True, blank=True, default=None)

    # Last ping time — updated every 10s by Flutter /api/ping/
    # If this is older than 15s, user is considered OFFLINE for matchmaking
    last_ping_time = models.DateTimeField(null=True, blank=True, default=None)
    
    # Last updated
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} — active:{self.is_active}"


class FCMDevice(models.Model):
    # user_id (Foreign Key): identified the token which user have
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    
    # fcm_token (String Unique): 
    fcm_token = models.CharField(max_length=500, unique=True)
    
    # device_type (String): android or ios
    device_type = models.CharField(max_length=50, default='android')
    
    # updated_at (Timestamp): LastTime Token
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.device_type}"

#Ping Usesers Active Table 
class Active_User(models.Model):
     user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
     last_ping_time = models.DateTimeField()

     def __str__(self):
         return f"User {self.user.id} - Pinged At: {self.last_ping_time}"