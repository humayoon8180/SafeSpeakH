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
        
        # Agar email pehle se hai ya password missing hai toh errors wapas bhejenge
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 2. LOGIN API
class LoginView(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        # Django ka 'authenticate' default username mangta hai. 
        # Humne serializers mein username ki jagah email save kiya tha, isliye yahan username=email bhej rahe hain.
        user = authenticate(username=email, password=password)

        if user is not None:
            # User theek hai! Ab uske liye naye JWT Tokens generate karo
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
            "id": user.id,              # 🟢 Yeh line add kar di gayi hai
            "name": user.first_name,
            "email": user.email,
            "date_joined": user.date_joined
        }, status=status.HTTP_200_OK)