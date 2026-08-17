from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    model = User
    # Add your custom fields to the admin panel view
    fieldsets = UserAdmin.fieldsets + (
        ('Verification & Profile', {'fields': ('face_verification', 'voice_verification', 'voice_score', 'country', 'proficiency_level', 'profile_image_url', 'rating', 'reports', 'total_calls')}),
    )

admin.site.register(User, CustomUserAdmin)