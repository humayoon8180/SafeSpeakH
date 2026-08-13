from datetime import timedelta
import requests as http_requests
from django.utils import timezone
from django.contrib.auth import authenticate
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, parser_classes, permission_classes, authentication_classes
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile, FCMDevice, UserActiva

from .serializers import UserRegistrationSerializer
from django.utils import timezone
import datetime
from dateutil.parser import parse
from firebase_admin import messaging
from .firebase_config import get_firebase_app
from .models import Active_User
PING_TIMEOUT_SECONDS = 20

# 1. REGISTER API
class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Create UserActiva row for this user so they are
            # immediately visible to the matchmaking system.
            UserActiva.objects.get_or_create(
                user_id=user.id,
                defaults={'is_active': False, 'is_on_call': False}
            )

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
        flat_errors = {field: msgs[0] for field, msgs in errors.items()}
        return Response({
            "success": False,
            "message": str(first_error),
            "data": flat_errors
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
        except Exception:
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


# ── 4. FACE VERIFICATION GATEWAY (Proxy to FastAPI AI Service) ────────────────
# Public endpoint — called during registration BEFORE the user has a token
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser])
def verify_face_gateway(request):
    """
    POST /api/verify-face/

    API Gateway: Receives live_image from Flutter, forwards it internally
    to the FastAPI AI microservice running on port 8001, and returns
    the exact JSON response back to the frontend.

    This keeps FastAPI hidden from the public internet (127.0.0.1 only).
    """
    FASTAPI_URL = "http://127.0.0.1:8001/verify/face/"

    live_image = request.FILES.get("live_image")
    if not live_image:
        return Response(
            {"status": "fail", "message": "No image uploaded. Please provide 'live_image'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Forward the image as multipart/form-data to FastAPI
        files = {"live_image": (live_image.name, live_image.read(), live_image.content_type)}
        ai_response = http_requests.post(FASTAPI_URL, files=files, timeout=90)
        return Response(ai_response.json(), status=ai_response.status_code)

    except http_requests.exceptions.RequestException:
        return Response(
            {
                "status": "fail",
                "message": "AI verification service is currently unavailable. Please try again later."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

##SetFcm Token Recived From Flutter
class SetFCMTokenView(APIView):
    # JWT authentication filhal bypass kar di hai
    permission_classes = [] 

    def post(self, request):
        user_id = request.data.get('user_id')
        fcm_token = request.data.get('fcmToken')
        device_type = request.data.get('device_type', 'android') # Default to android if not provided

        # Validation: check karein ke zaroori data bheja gaya hai ya nahi
        if not user_id or not fcm_token:
            return Response(
                {"success": False, "message": "user_id and fcm_token are required."}, 
                status=400
            )

        try:
            # Database mein token save ya update karein
            fcm_device, created = FCMDevice.objects.update_or_create(
                user_id=user_id,
                defaults={
                    'fcm_token': fcm_token,
                    'device_type': device_type
                }
            )
            
            return Response({
                "success": True, 
                "message": "FCM Token updated successfully.",
                "data": {
                    "user_id": user_id,
                    "fcmToken": fcm_token
                }
            }, status=200)
            
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)

##Ping Api Request 
class PingView(APIView):
    permission_classes = [] 

    def put(self, request): 
        user_id = request.data.get('user_id')
        
        # Note: Ab hum yahan request.data.get('ping_at') nahi mangwa rahe

        if not user_id:
            return Response({"success": False, "message": "user_id is required."}, status=400)

        try:
            # ==========================================
            # NAYA CODE: Backend ka apna live time
            # ==========================================
            ping_time = timezone.now()
            
            # Database mein update karein
            Active_User.objects.update_or_create(
                user_id=user_id,
                defaults={'last_ping_time': ping_time}
            )
            
            return Response({"success": True, "message": "Ping Recived Successfully"}, status=200)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)


##Call/initiate / api

class InitiateCallView(APIView):
    # user_id comes directly from the request body, no access token
    # required for this endpoint (matches the ping endpoint's pattern).
    permission_classes = [AllowAny]
 
    def post(self, request):
        caller_id = request.data.get('user_id')
        room_id = request.data.get('room_id')
 
        if not caller_id:
            return Response(
                {"success": False, "message": "user_id is required."},
                status=400
            )
 
        if not room_id:
            return Response(
                {"success": False, "message": "room_id is required."},
                status=400
            )
 
        now = timezone.now()
        thirty_seconds_ago = now - timedelta(seconds=30)
 
        with transaction.atomic():
            # -----------------------------------------------------------
            # STEP 1: Housekeeping — for every user in Active_User,
            # use update_or_create so users without a UserActiva row
            # (e.g. registered before this fix) get one automatically.
            # Mark fresh pingers active, stale pingers inactive.
            # -----------------------------------------------------------
            fresh_ping_ids = list(
                Active_User.objects
                .filter(last_ping_time__gte=thirty_seconds_ago)
                .values_list('user_id', flat=True)
            )
            stale_ping_ids = list(
                Active_User.objects
                .filter(last_ping_time__lt=thirty_seconds_ago)
                .values_list('user_id', flat=True)
            )

            # Ensure every fresh pinger has an active UserActiva row.
            for uid in fresh_ping_ids:
                UserActiva.objects.update_or_create(
                    user_id=uid,
                    defaults={'is_active': True}
                )

            # Mark stale pingers inactive and remove from Active_User.
            if stale_ping_ids:
                UserActiva.objects.filter(user_id__in=stale_ping_ids).update(is_active=False)
                Active_User.objects.filter(user_id__in=stale_ping_ids).delete()

            # -----------------------------------------------------------
            # STEP 2: Make sure the caller isn't already on a call.
            # -----------------------------------------------------------
            caller_status = UserActiva.objects.select_for_update().filter(user_id=caller_id).first()
            if caller_status and caller_status.is_on_call:
                return Response(
                    {"success": False, "message": "You are already on a call."},
                    status=400
                )

            # -----------------------------------------------------------
            # STEP 3: Find a candidate who is:
            #   - actively pinging (in Active_User with fresh ping)
            #   - not on a call (UserActiva.is_on_call=False)
            #   - not the caller themselves
            # This query works purely from Active_User — no cross-table
            # filter needed since we just synced UserActiva above.
            # -----------------------------------------------------------
            busy_user_ids = list(
                UserActiva.objects
                .filter(is_on_call=True)
                .values_list('user_id', flat=True)
            )

            candidate = (
                Active_User.objects
                .select_for_update(skip_locked=True)
                .filter(last_ping_time__gte=thirty_seconds_ago)
                .exclude(user_id=caller_id)
                .exclude(user_id__in=busy_user_ids)
                .order_by('?')
                .first()
            )

            if not candidate:
                return Response(
                    {"success": False, "message": "No active user found right now."},
                    status=404
                )

            target_user_id = candidate.user_id

            # Lock BOTH the caller and the candidate.
            # Neither is removed from Active_User.
            UserActiva.objects.filter(user_id__in=[caller_id, target_user_id]).update(
                is_on_call=True,
                call_locked_at=now,
            )
 # -----------------------------------------------------------
        # STEP 5: Fetch the candidate's FCM token AND send the push,
        # both inside ONE try/except block, so ANY unexpected failure
        # releases both locks instead of leaving them stuck.
        # -----------------------------------------------------------
        try:
            device_profile = FCMDevice.objects.get(user_id=target_user_id)
            fcm_token = device_profile.fcm_token

            if not fcm_token:
                raise ValueError("Partner has no FCM token.")

            get_firebase_app()
            current_timestamp = now.strftime("%H:%M:%S %m/%d/%Y")

            fcm_message = messaging.Message(
                data={
                    "caller_id": str(caller_id),
                    "room_id": str(room_id),
                    "sent_at": current_timestamp,
                },
                android=messaging.AndroidConfig(
                    ttl=datetime.timedelta(seconds=15),
                    priority="high"
                ),
                token=fcm_token,
            )
            messaging.send(fcm_message)

        except FCMDevice.DoesNotExist:
            UserActiva.objects.filter(user_id__in=[caller_id, target_user_id]).update(is_on_call=False)
            return Response(
                {"success": False, "message": "Partner profile not found."},
                status=404
            )
        except ValueError as e:
            UserActiva.objects.filter(user_id__in=[caller_id, target_user_id]).update(is_on_call=False)
            return Response(
                {"success": False, "message": str(e)},
                status=404
            )
        except messaging.UnregisteredError:
            UserActiva.objects.filter(user_id__in=[caller_id, target_user_id]).update(is_on_call=False)
            FCMDevice.objects.filter(user_id=target_user_id).delete()
            return Response(
                {"success": False, "message": "Partner's token expired."},
                status=410
            )
        except Exception as e:
            UserActiva.objects.filter(user_id__in=[caller_id, target_user_id]).update(is_on_call=False)
            return Response(
                {"success": False, "message": f"Call setup failed: {str(e)}"},
                status=500
            )

        # -----------------------------------------------------------
        # STEP 6: Success — tell User A who they're calling
        # -----------------------------------------------------------
        return Response({
            "success": True,
            "message": "Call initiated successfully.",
            "data": {
                "partner_id": target_user_id,
                "room_id": room_id
            }
        }, status=200)