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
            return Response({"message": "Account successfully created!"}, status=status.HTTP_201_CREATED)

        # Return validation errors if email already exists or fields are invalid
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 2. LOGIN API
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        # Reject request if email or password is missing
        if not email or not password:
            return Response(
                {"error": "Email and password are both required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Django's authenticate() requires username. Since we saved email as username,
        # we pass email.lower() to match the stored value exactly.
        user = authenticate(username=email.lower(), password=password)

        if user is not None:
            # Credentials valid — generate new JWT tokens for the user
            refresh = RefreshToken.for_user(user)
            return Response({
                "message": "Login successful!",
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "user": {
                    "name": user.first_name,
                    "email": user.email
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid email or password"}, status=status.HTTP_401_UNAUTHORIZED)


# 3. USER PROFILE API (Protected Route)
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,              # User ID included in response
            "name": user.first_name,
            "email": user.email,
            "date_joined": user.date_joined
        }, status=status.HTTP_200_OK)