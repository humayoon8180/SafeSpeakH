# api/serializers.py
# Register serializer with updated error response and verification fields

from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import CallDetails
User = get_user_model()
from .models import YouTubeVideo

##User Registration Serializer
class UserRegistrationSerializer(serializers.ModelSerializer):
    email    = serializers.EmailField(required=True)
    name     = serializers.CharField(source='first_name', required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    
    # Frontend se aane wale nayi verification fields
    face_verification = serializers.BooleanField(required=True)
    voice_verification = serializers.BooleanField(required=True)
    voice_score = serializers.FloatField(required=True)

    class Meta:
        model  = User
        fields = ('email', 'name', 'password', 'face_verification', 'voice_verification', 'voice_score')

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "User with this email already exists."
            )
        return value.lower()

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError(
                "Name must be at least 2 characters."
            )
        return value.strip()

    def create(self, validated_data):
        email      = validated_data['email']
        password   = validated_data['password']
        first_name = validated_data['first_name']
        
        # Profile data directly saved in the new custom User model
        face_verification = validated_data.pop('face_verification', False)
        voice_verification = validated_data.pop('voice_verification', False)
        voice_score = validated_data.pop('voice_score', 0.0)

        user = User.objects.create_user(
            username   = email,
            email      = email,
            password   = password,
            first_name = first_name,
            face_verification = face_verification,
            voice_verification = voice_verification,
            voice_score = voice_score
        )

        return user

###call details serializer
class CallDetailsSerializer(serializers.ModelSerializer):
    caller_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='caller'
    )
    speaking_partner_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='speaking_partner'
    )

    class Meta:
        model = CallDetails
        fields = ['caller_id', 'speaking_partner_id', 'rating', 'feedback', 'call_duration']
        
        # Override the automatic UniqueConstraint check so we can use update_or_create
        validators = []


##youtube video serializer
class YouTubeVideoSerializer(serializers.ModelSerializer):
    # id is read-only — auto-assigned by DB on POST, returned in GET response
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = YouTubeVideo
        fields = ['id', 'title', 'description', 'url']