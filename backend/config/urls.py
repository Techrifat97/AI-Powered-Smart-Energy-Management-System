"""
URL configuration for the Smart Energy Management System.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Subsystem-prefixed routes (no Django URL namespaces).
    path('api/monitoring/', include('monitoring.urls')),
    path('api/coach/', include('coach.urls')),
    path('api/analysis/', include('analysis.urls')),

    # Shared convenience prefix for subsystem APIs.
    path('api/', include('monitoring.urls')),
    path('api/', include('coach.urls')),
    path('api/', include('analysis.urls')),
]
