# =============================================================================
# api/views.py
# REST API Controllers & Gateway Handlers for the SafeSpeak Platform.
#
# Architectural Overview:
#   1. Authentication & Onboarding (Register, Login, Profile)
#   2. Biometric Verification Gateways (Proxying to local FastAPI AI microservice)
#   3. Push Notifications & Client Presence (FCM Token, Server Heartbeat/Ping)
#   4. Matchmaking & Call Orchestration (Atomic candidate selection, Call Locking)
#   5. WebRTC / Agora Signaling (Cryptographic channel token issuance)
#   6. Post-Session Analytics (Idempotent ratings, feedback history audit)
#   7. Moderation & Trust (Account status enforcement, User appeals)
# =============================================================================

import os
import time
import datetime
from datetime import timedelta
from dateutil.parser import parse
import requests as http_requests

from django.utils import timezone
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, parser_classes, permission_classes, authentication_classes
from rest_framework_simplejwt.tokens import RefreshToken

from firebase_admin import messaging
from agora_token_builder import RtcTokenBuilder

from .firebase_config import get_firebase_app
from .models import (
    FCMDevice,
    UserActiva,
    AccountStatus,
    Appeal,
    Active_User,
    CallDetails,
    YouTubeVideo
)
from .serializers import (
    UserRegistrationSerializer,
    CallDetailsSerializer,
    YouTubeVideoSerializer
)


# ---------------------------------------------------------------------------
# 1. USER REGISTRATION
# ---------------------------------------------------------------------------
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

            # Issue a JWT token pair immediately on registration so the client
            # can proceed to the authenticated home screen without a separate login step.
            refresh = RefreshToken.for_user(user)

            # Return a consistent envelope matching the login response contract.
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

        # If email already exists, return a clean message only
        if 'email' in errors:
            email_error = str(errors['email'][0])
            if 'already exists' in email_error.lower():
                return Response({
                    "success": False,
                    "message": "User with this email already exists."
                }, status=status.HTTP_400_BAD_REQUEST)

        first_error = next(iter(errors.values()))[0]
        flat_errors = {field: msgs[0] for field, msgs in errors.items()}
        return Response({
            "success": False,
            "message": str(first_error),
            "data": flat_errors
        }, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------------------------------------------------------
# 2. LOGIN
# ---------------------------------------------------------------------------
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email    = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({
                "success": False,
                "message": "Email and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Django's authenticate normalises the username to lowercase to match
        # the email stored during registration.
        user = authenticate(
            username=email.lower(),
            password=password
        )

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                "success": True,
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
            "success": False,
            "message": "Email or password is incorrect."
        }, status=status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# 3. USER PROFILE (Protected — requires Bearer token)
# ---------------------------------------------------------------------------
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "success": True,
            "user": {
                "id":                 user.id,
                "name":               user.first_name,
                "email":              user.email,
                "date_joined":        user.date_joined,
                "face_verification":  user.face_verification,
                "voice_verification": user.voice_verification,
                "voice_score":        user.voice_score,
                "total_calls":        user.total_calls,
                "profile_image_url":  user.profile_image_url,
                "rating":             user.rating,
                "proficiency_level":  user.proficiency_level,
                "reports":            user.reports,
                "country":            user.country
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
            {"success": False,
             "message": "No image uploaded. Please provide 'live_image'."},

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
                "success": False,
                "message": "AI verification service is currently unavailable. Please try again later."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


# ── 5. VOICE VERIFICATION GATEWAY (Proxy to FastAPI AI Service) ───────────────
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser])
def verify_voice_gateway(request):
    """
    POST /api/verify-voice/

    API Gateway: Receives audio_file and face_verified from Flutter, 
    forwards it to the FastAPI AI microservice on port 8001.
    """
    FASTAPI_URL = "http://127.0.0.1:8001/verify/voice/"

    audio_file = request.FILES.get("audio_file")
    user_id = request.data.get("user_id", 0)
    face_verified = request.data.get("face_verified", "False")

    if not audio_file:
        return Response(
            {"success": False, "message": "No audio uploaded. Please provide 'audio_file'."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        files = {"audio_file": (audio_file.name, audio_file.read(), audio_file.content_type)}
        data = {"user_id": user_id, "face_verified": face_verified}
        ai_response = http_requests.post(FASTAPI_URL, files=files, data=data, timeout=90)
        return Response(ai_response.json(), status=ai_response.status_code)

    except http_requests.exceptions.RequestException as e:
        return Response(
            {
                "success": False,
                "message": f"AI Voice service unavailable: {str(e)}"
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


# ---------------------------------------------------------------------------
# 6. FCM TOKEN REGISTRATION
# Stores or refreshes the device's Firebase Cloud Messaging push token.
# Authentication is intentionally relaxed here: the token is registered
# immediately after login before the client has set the Authorization header.
# ---------------------------------------------------------------------------
class SetFCMTokenView(APIView):
    permission_classes = []

    def post(self, request):
        user_id     = request.data.get('user_id')
        fcm_token   = request.data.get('fcmToken')
        device_type = request.data.get('device_type', 'android')

        if not user_id or not fcm_token:
            return Response(
                {"success": False, "message": "user_id and fcm_token are required."},
                status=400
            )

        try:
            # Upsert the token: a user replacing their device or reinstalling
            # the app will naturally receive a new FCM token.
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
                    "user_id":  user_id,
                    "fcmToken": fcm_token
                }
            }, status=200)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)


# ---------------------------------------------------------------------------
# 7. HEARTBEAT / PING
# Receives a periodic keep-alive signal from the Flutter client and records
# the server-side timestamp in Active_User. The matchmaking engine treats any
# user whose last_ping_time is older than 30 seconds as offline and excludes
# them from the candidate pool.
#
# Design note: The timestamp is set server-side (timezone.now()) rather than
# trusting a client-supplied value, preventing clock-skew from corrupting
# the online-status window.
# ---------------------------------------------------------------------------
class PingView(APIView):
    permission_classes = []

    def put(self, request):
        user_id = request.data.get('user_id')

        if not user_id:
            return Response({"success": False, "message": "user_id is required."}, status=400)

        try:
            # Always use the authoritative server clock to stamp the ping.
            ping_time = timezone.now()

            Active_User.objects.update_or_create(
                user_id=user_id,
                defaults={'last_ping_time': ping_time}
            )

            return Response({"success": True, "message": "Ping received successfully."}, status=200)

        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=500)


# ---------------------------------------------------------------------------
# 8. CALL INITIATION & MATCHMAKING
# ---------------------------------------------------------------------------
class InitiateCallView(APIView):
    # This endpoint identifies the caller by user_id in the request body
    # rather than a Bearer token, consistent with the ping endpoint contract.
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
            # get_or_create ensures the caller gets added to UserActiva 
            # even if they never pinged before calling!
            # -----------------------------------------------------------
            caller_status, _ = UserActiva.objects.select_for_update().get_or_create(user_id=caller_id)
            if caller_status.is_on_call:
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
            # -----------------------------------------------------------
            # Retrieve caller metadata for notification payload
            # -----------------------------------------------------------
            from django.contrib.auth import get_user_model
            User = get_user_model()
            caller_user = User.objects.filter(id=caller_id).first()

            # Safely extract metadata with fallback values if profile data is incomplete
            caller_name = caller_user.first_name if caller_user and caller_user.first_name else "Unknown"
            caller_image = caller_user.profile_image_url if caller_user and caller_user.profile_image_url else ""
            caller_country = caller_user.country if caller_user and caller_user.country else ""
            caller_rating = str(caller_user.rating) if caller_user else "0.0"
            # -----------------------------------------------------------

            fcm_message = messaging.Message(
                # notification block: makes Android OS wake the app
                # and show a system tray notification even if the app
                # is in the background or completely killed.
                notification=messaging.Notification(
                    title="Incoming Call",
                    body=f"{caller_name} wants to talk to you on SafeSpeak!",
                ),
                data={
                    "caller_id": str(caller_id),
                    "room_id": str(room_id),
                    "sent_at": current_timestamp,
                    "caller_name": caller_name,
                    "caller_image": caller_image,
                    "caller_country": caller_country,
                    "caller_rating": caller_rating,
                },
                android=messaging.AndroidConfig(
                    # 30 seconds gives enough time for slow networks
                    # and Doze mode to wake up and deliver the message.
                    ttl=datetime.timedelta(seconds=30),
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="incoming_call_channel",
                        priority="max",
                        default_vibrate_timings=True,
                    ),
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
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            partner = User.objects.get(id=target_user_id)
            
            # --- Safely Extract Partner Details (Fallback check applied) ---
            partner_name = partner.first_name if partner.first_name else "Unknown"
            partner_country = partner.country if partner.country else "Unknown"
            partner_image = partner.profile_image_url if partner.profile_image_url else ""
            partner_rating = partner.rating if partner.rating else 0.0
            
            partner_details = {
                "name": partner_name,
                "email": partner.email,
                "profile_image_url": partner_image,
                "country": partner_country,
                "rating": partner_rating,
            }
            
        except User.DoesNotExist:
            partner_details = None

        # -----------------------------------------------------------
        # STEP 7: Success — tell User A who they're calling
        # -----------------------------------------------------------
        return Response({
            "success": True,
            "message": "Call initiated successfully.",
            "data": {
                "partner_id": target_user_id,
                "room_id": room_id,
                "partner_details": partner_details
            }
        }, status=status.HTTP_200_OK)

# ---------------------------------------------------------------------------
# 9. AGORA RTC TOKEN GENERATION
# Issues short-lived RTC channel tokens for secure audio communication.
# ---------------------------------------------------------------------------
class GenerateAgoraTokenView(APIView):
    def post(self, request):
        # Extract target room identifier from request
        channel_name = request.data.get('room_id')

        # Default UID to 0 if not supplied by client (allows Agora to allocate dynamically)
        uid = request.data.get('uid', 0)

        if not channel_name:
            return Response({"success": False, "error": "room_id is required"}, status=400)

        # Retrieve Agora credentials from environment configuration
        app_id = os.environ.get('AGORA_APP_ID')
        app_certificate = os.environ.get('AGORA_APP_CERTIFICATE')

        # Token expiration policy: 3600 seconds (1 hour) validity window
        expiration_time_in_seconds = 3600
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_time_in_seconds
        role = 1  # Role 1 corresponds to Broadcaster (bidirectional audio streaming)

        # Generate cryptographic RTC token via Agora SDK builder
        try:
            token = RtcTokenBuilder.buildTokenWithUid(
                app_id,
                app_certificate,
                channel_name,
                int(uid),
                role,
                privilege_expired_ts
            )

            # Return token envelope to client
            return Response({
                "success": True,
                "token": token,
                "room_id": channel_name,
                "uid": uid
            }, status=200)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# 10. CALL TERMINATION / RELEASE
# Releases the presence lock for the terminating participant.
# ---------------------------------------------------------------------------
class EndCallView(APIView):
    def post(self, request):
        user_id = request.data.get('user_id')

        if not user_id:
            return Response({"success": False, "error": "user_id is required"}, status=400)

        # Release active call state lock and clear timestamp
        UserActiva.objects.filter(user_id=user_id).update(
            is_on_call=False,
            call_locked_at=None
        )

        return Response({
            "success": True,
            "message": "Call ended successfully. Users are now free!"
        }, status=200)

# ---------------------------------------------------------------------------
# 11. CALL FEEDBACK & RATING SUBMISSION
# Persists post-call participant feedback and rating metrics.
# ---------------------------------------------------------------------------
class SubmitCallDetailsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CallDetailsSerializer(data=request.data)

        if serializer.is_valid():
            speaking_partner = serializer.validated_data['speaking_partner']
            caller = serializer.validated_data['caller']

            # Business rule: Disallow self-rating submissions
            if caller == speaking_partner:
                return Response(
                    {"success": False, "message": "You cannot rate yourself."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Idempotent persistence: Update existing record for repeat pairings
            details_obj, created = CallDetails.objects.update_or_create(
                caller=caller,
                speaking_partner=speaking_partner,
                defaults={
                    'rating': serializer.validated_data.get('rating'),
                    'feedback': serializer.validated_data.get('feedback', ''),
                    'call_duration': serializer.validated_data['call_duration']
                }
            )

            return_data = CallDetailsSerializer(details_obj).data

            return Response(
                {
                    "success": True,
                    "message": "Call details successfully created!" if created else "Call details successfully updated!",
                    "data": return_data
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )

        # Handle validation failures on malformed or missing fields
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


# ---------------------------------------------------------------------------
# 12. CALL HISTORY & FEEDBACK AUDIT
# Returns paginated historical feedback submitted by a specific caller.
# ---------------------------------------------------------------------------
class UserFeedbackHistoryView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        # Extract caller ID from query parameters
        caller_id = request.GET.get('caller_id')

        # Validate presence of mandatory filter parameter
        if not caller_id:
            return Response(
                {"success": False, "message": "caller_id is required as a URL query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Query recent feedback records ordered chronologically descending (limit 50)
            history_records = CallDetails.objects.filter(
                caller_id=caller_id
            ).order_by('-created_at')[:50]

            # Serialize records for API response
            serializer = CallDetailsSerializer(history_records, many=True)

            return Response({
                "success": True,
                "message": "Feedback history fetched successfully.",
                "total_records": len(history_records),
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # Internal server error handler
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ---------------------------------------------------------------------------
# 13. CURATED RESOURCE / YOUTUBE VIDEO FEED
# Provides collection retrieval and ingestion for educational video resources.
# ---------------------------------------------------------------------------
class YouTubeVideoView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """Retrieves all curated video records ordered newest first."""
        try:
            videos = YouTubeVideo.objects.all().order_by('-id')
            serializer = YouTubeVideoSerializer(videos, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"success": False, "message": f"Internal Server Error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Ingests a new educational video resource into the catalog."""
        try:
            serializer = YouTubeVideoSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {"success": True, "message": "Video has been successfully added!"},
                    status=status.HTTP_201_CREATED
                )

            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # Catch any unexpected exceptions during the creation process
            return Response(
                {"success": False, "message": f"Internal Server Error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ---------------------------------------------------------------------------
# 14. ACCOUNT TERMINATION
# Administrative endpoint to transition a user account into terminated state.
# ---------------------------------------------------------------------------
class TerminateAccountView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        user_id = request.data.get('user_id')
        reason  = request.data.get('reason')

        if not user_id or not reason:
            return Response({
                "success": False,
                "message": "user_id and reason are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate that the targeted user exists
        try:
            User = get_user_model()
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "message": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Retrieve or initialize the user's account status record
        account_status, _ = AccountStatus.objects.get_or_create(
            user=user,
            defaults={'is_active': True, 'is_terminated': False}
        )

        # Guard against redundant termination calls
        if account_status.is_terminated:
            return Response({
                "success": False,
                "message": "This account is already terminated."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Transition status flags and commit changes
        account_status.is_active     = False
        account_status.is_terminated = True
        account_status.save()

        return Response({
            "success": True,
            "message": f"Account of {user.email} has been terminated.",
            "data": {
                "user_id":       user.id,
                "email":         user.email,
                "is_active":     account_status.is_active,
                "is_terminated": account_status.is_terminated,
            }
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# 15. USER APPEAL SUBMISSION
# Allows terminated users to submit an appeal. Updates existing records
# idempotently by email. Account reactivation is performed manually by an admin.
# ---------------------------------------------------------------------------
class AppealView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email   = request.data.get('email')
        message = request.data.get('message')

        if not email or not message:
            return Response({
                "success": False,
                "message": "email and message are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent persistence: Update message for existing appeal from same email
        appeal, created = Appeal.objects.update_or_create(
            email=email.lower().strip(),
            defaults={'message': message}
        )
        return Response({
            "success": True,
            "message": "Your appeal has been submitted successfully. We will Review it and notify you",
            "data": {
                "email": email.lower().strip()
            }
        }, status=status.HTTP_201_CREATED)