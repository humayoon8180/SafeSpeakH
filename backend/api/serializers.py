# api/serializers.py
# Register serializer with updated error response

from django.contrib.auth.models import User
from rest_framework import serializers
from .models import UserProfile

class UserRegistrationSerializer(serializers.ModelSerializer):
    email    = serializers.EmailField(required=True)
    name     = serializers.CharField(source='first_name', required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'}
    )

    class Meta:
        model  = User
        fields = ('email', 'name', 'password')

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

        user = User.objects.create_user(
            username   = email,
            email      = email,
            password   = password,
            first_name = first_name
        )

        # Create UserProfile automatically
        UserProfile.objects.create(user=user)
        return user