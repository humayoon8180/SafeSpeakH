# api/views.py
# All API views with updated response format

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserRegistrationSerializer

# 1. REGISTER API
class RegisterView(APIView):
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "status":  "success",
                "message": "Account created successfully"
            }, status=status.HTTP_201_CREATED)

        # Get first error message
        errors = serializer.errors
        first_error = next(iter(errors.values()))[0]
        return Response({
            "status":  "fail",
            "message": str(first_error)
        }, status=status.HTTP_400_BAD_REQUEST)


# 2. LOGIN API
class LoginView(APIView):
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
                "status":        "success",
                "message":       "Login successful",
                "access_token":  str(refresh.access_token),
                "refresh_token": str(refresh),
                "user": {
                    "id":    user.id,
                    "name":  user.first_name,
                    "email": user.email
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

        # Get or create profile
        profile, _ = user.userprofile.__class__.objects.get_or_create(
            user=user
        )

        return Response({
            "status": "success",
            "user": {
                "id":                user.id,
                "name":              user.first_name,
                "email":             user.email,
                "date_joined":       user.date_joined,
                "face_verification": profile.face_verification,
                "voice_verification": profile.voice_verification,
                "voice_score":       profile.voice_score
            }
        }, status=status.HTTP_200_OK)