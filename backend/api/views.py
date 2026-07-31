# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserRegistrationSerializer
from .models import UserProfile
from rest_framework.permissions import AllowAny

# 1. REGISTER API
class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Signup successful hone par foran token generate karna
            refresh = RefreshToken.for_user(user)
            
            # Standard Format as requested by frontend
            return Response({
                "success": True,
                "message": "Account created successfully",
                "data": {
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "user": {
                        "id": user.id,
                        "name": user.first_name,
                        "email": user.email,
                        "face_verification": request.data.get('face_verification'),
                        "voice_verification": request.data.get('voice_verification'),
                        "voice_score": request.data.get('voice_score')
                    }
                }
            }, status=status.HTTP_201_CREATED)

        # Formatting Errors 
        errors = serializer.errors
        first_error = next(iter(errors.values()))[0]
        return Response({
            "success": False,
            "message": str(first_error),
            "data": errors
        }, status=status.HTTP_400_BAD_REQUEST)

##Login Api
class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email    = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({
                "status":  "fail",
                "message": "Email and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(
            username=email.lower(),
            password=password
        )

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                "status":  "success",
                "message": "Login successful",
                "data": {
                    "access_token":  str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "user": {
                        "id":    user.id,
                        "name":  user.first_name,
                        "email": user.email
                    }
                }
            }, status=status.HTTP_200_OK)

        return Response({
            "status":  "fail",
            "message": "Email or password is incorrect."
        }, status=status.HTTP_401_UNAUTHORIZED)

# 3. PROFILE API (Protected)
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        try:
            profile, _ = UserProfile.objects.get_or_create(user=user)
        except Exception as e:
            # Handle Server Error 500
            return Response({
                "status":  "fail",
                "message": "Internal Server Error occurred while fetching profile."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "status": "success",
            "user": {
                "id":                 user.id,
                "name":               user.first_name,
                "email":              user.email,
                "date_joined":        user.date_joined,
                "face_verification":  profile.face_verification,
                "voice_verification": profile.voice_verification,
                "voice_score":        profile.voice_score,
                # --- New Fields Has been added---
                "total_calls":        profile.total_calls,
                "profile_image_url":  profile.profile_image_url,
                "rating":             profile.rating,
                "proficiency_level":  profile.proficiency_level,
                "reports":            profile.reports,
                "country":            profile.country
            }
        }, status=status.HTTP_200_OK)