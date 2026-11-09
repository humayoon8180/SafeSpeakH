# =============================================================================
# api/serializers.py
# Request/response serializers for the SafeSpeak REST API.
#
# Serializers handle input validation, field-level coercion, and controlled
# object creation. Business logic (token issuance, side-effect model creation)
# is intentionally kept in views, not serializers.
# =============================================================================

from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import CallDetails, YouTubeVideo

User = get_user_model()


# ---------------------------------------------------------------------------
# UserRegistrationSerializer
# Validates and creates a new User account including biometric verification
# results captured during the onboarding flow.
#
# Design decisions:
#   - 'name' maps to User.first_name via the 'source' kwarg to keep the
#     API surface idiomatic while preserving Django's internal field naming.
#   - Verification fields (face_verification, voice_verification, voice_score)
#     are accepted as required inputs because they are set at registration
#     time by the AI verification pipeline, not modifiable post-registration.
#   - Email uniqueness is enforced with a case-insensitive lookup to prevent
#     duplicate accounts via capitalisation variants.
# ---------------------------------------------------------------------------
class UserRegistrationSerializer(serializers.ModelSerializer):
    email    = serializers.EmailField(required=True)
    name     = serializers.CharField(source='first_name', required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )

    # Biometric verification results forwarded from the AI pipeline.
    face_verification  = serializers.BooleanField(required=True)
    voice_verification = serializers.BooleanField(required=True)
    voice_score        = serializers.FloatField(required=True)

    class Meta:
        model  = User
        fields = ('email', 'name', 'password', 'face_verification', 'voice_verification', 'voice_score')

    def validate_email(self, value):
        # Case-insensitive uniqueness check; normalise to lowercase on success.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value.lower()

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        return value.strip()

    def create(self, validated_data):
        # Extract verification fields before passing to create_user, as they
        # are not standard AbstractUser fields and must be set explicitly.
        face_verification  = validated_data.pop('face_verification', False)
        voice_verification = validated_data.pop('voice_verification', False)
        voice_score        = validated_data.pop('voice_score', 0.0)

        user = User.objects.create_user(
            username           = validated_data['email'],
            email              = validated_data['email'],
            password           = validated_data['password'],
            first_name         = validated_data['first_name'],
            face_verification  = face_verification,
            voice_verification = voice_verification,
            voice_score        = voice_score
        )
        return user


# ---------------------------------------------------------------------------
# CallDetailsSerializer
# Serializes post-call rating submissions.
#
# PrimaryKeyRelatedField is used for caller and speaking_partner so that
# the client sends integer IDs rather than nested user objects, keeping the
# payload minimal.
#
# The built-in UniqueConstraint validator is suppressed (validators=[]) to
# allow the view to use update_or_create semantics — subsequent calls between
# the same pair update the existing record rather than raising a 400 error.
# ---------------------------------------------------------------------------
class CallDetailsSerializer(serializers.ModelSerializer):
    caller_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='caller'
    )
    speaking_partner_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='speaking_partner'
    )

    class Meta:
        model      = CallDetails
        fields     = ['caller_id', 'speaking_partner_id', 'rating', 'feedback', 'call_duration']
        # Suppress automatic UniqueConstraint validation to support
        # update_or_create in the view layer.
        validators = []


# ---------------------------------------------------------------------------
# YouTubeVideoSerializer
# Full CRUD serializer for the curated learning content feed.
# The 'id' field is explicitly declared as read-only so that it is returned
# in GET responses but ignored (and not required) in POST requests.
# ---------------------------------------------------------------------------
class YouTubeVideoSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model  = YouTubeVideo
        fields = ['id', 'title', 'description', 'url']