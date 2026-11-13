"""
URL configuration for the Smart Energy Management System.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication & Accounts
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/accounts/', include('accounts.urls')),

    # Subsystem-prefixed routes (no Django URL namespaces).
    path('api/monitoring/', include('monitoring.urls')),
    path('api/coach/', include('coach.urls')),
    path('api/analysis/', include('analysis.urls')),

    # Shared convenience prefix for subsystem APIs.
    path('api/', include('accounts.urls')),
    path('api/', include('monitoring.urls')),
    path('api/', include('coach.urls')),
    path('api/', include('analysis.urls')),
]
