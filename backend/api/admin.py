# =============================================================================
# api/admin.py
# Django Admin site registrations for the SafeSpeak platform models.
#
# Admin classes are kept intentionally lean: list_display, search_fields, and
# list_filter are configured for operational efficiency. All account status
# changes (termination and reinstatement) are performed manually here by
# authorised administrators after reviewing user appeals.
# =============================================================================

from django.contrib import admin
from .models import User, AccountStatus, Appeal


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    # Surface the user ID as the first column to simplify cross-referencing
    # with API request logs and support tickets.
    list_display  = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('id', 'username', 'email')
    ordering      = ('id',)


@admin.register(AccountStatus)
class AccountStatusAdmin(admin.ModelAdmin):
    # Administrators use this view to manually reinstate terminated accounts
    # after reviewing the corresponding Appeal record.
    list_display  = ('id', 'user', 'is_active', 'is_terminated', 'created_at')
    search_fields = ('user__email',)
    list_filter   = ('is_active', 'is_terminated')
    ordering      = ('-created_at',)


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    # Displays appeal messages inline so administrators can read and act on
    # them without opening individual records.
    list_display  = ('id', 'email', 'message', 'created_at')
    search_fields = ('email', 'message')
    ordering      = ('-created_at',)
