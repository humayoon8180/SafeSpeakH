from django.contrib.auth.models import User
from rest_framework import serializers

class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    # Flutter se 'name' aayega, aur Django isay 'first_name' mein save karega
    name = serializers.CharField(source='first_name', required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('email', 'name', 'password') # 'name' add kar diya

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Yeh email pehle se registered hai.")
        return value

    def create(self, validated_data):
        email = validated_data['email']
        password = validated_data['password']
        # source='first_name' ki wajah se validated_data mein yeh 'first_name' ke naam se aayega
        first_name = validated_data['first_name']

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name # Yahan name save ho raha hai
        )
        return user