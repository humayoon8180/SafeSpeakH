from django.contrib import admin
from .models import User

@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    # 'id' add karne se table ke shuru mein user ID show hone lagegi
    list_display = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff')
    
    search_fields = ('id', 'username', 'email')
    ordering = ('id',)