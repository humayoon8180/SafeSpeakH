from django.contrib.auth.models import User
from rest_framework import serializers

class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    # Flutter sends 'name', Django saves it as 'first_name'
    name = serializers.CharField(source='first_name', required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, min_length=8)

    class Meta:
        model = User
        fields = ('email', 'name', 'password') # 'name' mapped to first_name

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value.lower()

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        return value.strip()

    def create(self, validated_data):
        email = validated_data['email']
        password = validated_data['password']
        # Due to source='first_name', validated_data contains 'first_name' key
        first_name = validated_data['first_name']

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name  # Saving display name here
        )
        return user