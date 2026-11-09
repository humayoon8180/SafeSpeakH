from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Mount application REST API routing under the /api/ prefix
    path('api/', include('api.urls')), 
]