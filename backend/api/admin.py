from django.contrib import admin
from .models import UserProfile

# Yeh line UserProfile ko admin panel mein show kar degi
admin.site.register(UserProfile)