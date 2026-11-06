"""
URL configuration for the Smart Energy Management System.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Subsystem Namespaced APIs
    path('api/monitoring/', include('monitoring.urls')),
    path('api/coach/', include('coach.urls')),

    # Convenience shortcuts for direct demo presentation
    path('api/', include('monitoring.urls')),
    path('api/', include('coach.urls')),
]
