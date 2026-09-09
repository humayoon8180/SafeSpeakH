from django.contrib import admin
from .models import User, AccountStatus, Appeal

@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('id', 'username', 'email')
    ordering = ('id',)


@admin.register(AccountStatus)
class AccountStatusAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'is_active', 'is_terminated', 'created_at')
    search_fields = ('user__email',)
    list_filter   = ('is_active', 'is_terminated')
    ordering      = ('-created_at',)


@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display  = ('id', 'email', 'message', 'created_at')
    search_fields = ('email', 'message')
    ordering      = ('-created_at',)
