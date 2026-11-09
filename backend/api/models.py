# =============================================================================
# api/models.py
# Domain models for the SafeSpeak platform.
#
# Architecture notes:
#   - User extends AbstractUser and maps to the existing 'auth_user' table,
#     adding biometric verification flags and profile metadata columns.
#   - UserActiva is the real-time presence table, updated via periodic pings
#     from the client and consumed by the matchmaking engine.
#   - FCMDevice stores Firebase Cloud Messaging push tokens per user device.
#   - Active_User is a lightweight heartbeat table used exclusively by the
#     matchmaking query to determine online eligibility.
#   - CallDetails captures post-call ratings and feedback, enforcing a
#     one-record-per-caller-per-partner constraint at the database level.
#   - AccountStatus tracks administrative termination state per user.
#   - Appeal stores user-submitted reinstatement requests for admin review.
# =============================================================================

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


# ---------------------------------------------------------------------------
# Custom User Model
# Extends Django's AbstractUser to add biometric verification status and
# platform-specific profile fields. Mapped to the existing 'auth_user' table
# to avoid a schema migration on the authentication table.
# ---------------------------------------------------------------------------
class User(AbstractUser):
    face_verification  = models.BooleanField(default=False)
    voice_verification = models.BooleanField(default=False)
    voice_score        = models.FloatField(default=0.0)

    # Extended profile fields — all nullable to support incremental onboarding.
    country           = models.CharField(max_length=100, blank=True, null=True)
    proficiency_level = models.CharField(max_length=100, blank=True, null=True)
    profile_image_url = models.URLField(max_length=1000, blank=True, null=True)
    rating            = models.FloatField(default=0.0)
    reports           = models.IntegerField(default=0)
    total_calls       = models.IntegerField(default=0)

    class Meta:
        # Reuse the existing Django auth table rather than creating a new one.
        db_table = 'auth_user'

    def __str__(self):
        return self.email or self.username


# ---------------------------------------------------------------------------
# UserActiva — Real-time Presence & Call Lock Table
# One row per user. Maintained by the ping endpoint and the matchmaking engine.
# Primary key is the User FK to enforce a strict one-to-one relationship
# without a redundant surrogate key.
# ---------------------------------------------------------------------------
class UserActiva(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='activa',
        primary_key=True
    )

    # Legacy FCM token field — superseded by FCMDevice but retained for
    # backward compatibility with older client builds.
    fcm_token = models.CharField(max_length=500, blank=True, default='')

    # True when the client is in the foreground and actively pinging.
    # Set to True by the matchmaking housekeeping step; cleared on stale ping.
    is_active = models.BooleanField(default=False)

    # Exclusive call lock flag. Set atomically alongside call_locked_at to
    # prevent the same user from being matched into two concurrent calls.
    is_on_call = models.BooleanField(default=False)

    # Timestamp when is_on_call was set. Used to detect and release stale
    # locks (e.g. when a client crashes without calling /api/call/end/).
    call_locked_at = models.DateTimeField(null=True, blank=True, default=None)

    # Wall-clock time of the most recent ping received from the client.
    # Users whose last_ping_time is older than 30 seconds are excluded from
    # matchmaking and treated as offline.
    last_ping_time = models.DateTimeField(null=True, blank=True, default=None)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} — active:{self.is_active}"


# ---------------------------------------------------------------------------
# FCMDevice — Firebase Push Notification Token Registry
# A user may register multiple devices over time; update_or_create on user_id
# ensures only one active token is stored per user at any given time.
# ---------------------------------------------------------------------------
class FCMDevice(models.Model):
    # Many-to-one with User: in practice, only the most recent token is used.
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    # Unique constraint prevents duplicate token registrations across users.
    fcm_token   = models.CharField(max_length=500, unique=True)
    device_type = models.CharField(max_length=50, default='android')
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.device_type}"


# ---------------------------------------------------------------------------
# Active_User — Lightweight Heartbeat Table
# Records the most recent ping timestamp per user. The matchmaking engine
# queries this table to build the pool of eligible candidates.
# Rows are deleted when a user's ping becomes stale (> 30 seconds old).
# ---------------------------------------------------------------------------
class Active_User(models.Model):
    user           = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    last_ping_time = models.DateTimeField()

    def __str__(self):
        return f"User {self.user.id} - Last Ping: {self.last_ping_time}"


# ---------------------------------------------------------------------------
# CallDetails — Post-Call Rating & Feedback Record
# Captures the rating and optional free-text feedback a caller submits after
# a session ends. A unique constraint at the DB level ensures one record per
# (caller, speaking_partner) pair; subsequent calls update the existing row.
# ---------------------------------------------------------------------------
class CallDetails(models.Model):
    caller           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='call_details_given')
    speaking_partner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='call_details_received')

    rating = models.FloatField(
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        null=True, blank=True
    )
    feedback      = models.TextField(blank=True, null=True)
    call_duration = models.CharField(
        max_length=20,
        help_text="Duration in MM:SS format",
        default="00:00"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Enforce one rating record per ordered caller-partner pair.
            # Re-calls between the same two users update this row in place.
            models.UniqueConstraint(
                fields=['caller', 'speaking_partner'],
                name='one_call_detail_per_caller_per_partner'
            ),
            # Rating must be NULL (not yet rated) or within the 1.0–5.0 band.
            models.CheckConstraint(
                check=models.Q(rating__isnull=True) | (
                    models.Q(rating__gte=1.0) & models.Q(rating__lte=5.0)
                ),
                name='rating_between_1_and_5_or_null'
            ),
        ]

    def __str__(self):
        return f"{self.caller} rated {self.speaking_partner} — {self.rating} stars"


# ---------------------------------------------------------------------------
# YouTubeVideo — Curated Learning Content Registry
# Stores admin-curated YouTube video metadata for the in-app resource feed.
# ---------------------------------------------------------------------------
class YouTubeVideo(models.Model):
    title       = models.CharField(max_length=255)
    description = models.TextField()
    url         = models.URLField()

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# AccountStatus — Administrative Account State
# Tracks whether a user account is in good standing or has been terminated
# by an administrator. Status transitions are performed manually via the
# Django admin panel or the /api/terminate/ endpoint.
# ---------------------------------------------------------------------------
class AccountStatus(models.Model):
    user          = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_status')
    is_active     = models.BooleanField(default=True)
    is_terminated = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} — Active: {self.is_active}"


# ---------------------------------------------------------------------------
# Appeal — User Reinstatement Request
# Stores appeal messages submitted by users whose accounts have been
# terminated. Status reinstatement is performed manually by an administrator
# after reviewing the appeal; this model itself does not trigger any
# automatic state changes. Duplicate appeals from the same email address
# overwrite the previous record via update_or_create in the view layer.
# ---------------------------------------------------------------------------
class Appeal(models.Model):
    email      = models.EmailField()
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Appeal from {self.email}"