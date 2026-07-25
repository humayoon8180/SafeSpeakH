from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Yeh line aapke 'api' folder wali urls.py ko is main project se link karti hai
    path('api/', include('api.urls')), 
]