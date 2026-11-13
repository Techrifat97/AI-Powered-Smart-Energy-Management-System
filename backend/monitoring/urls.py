from django.urls import path
from .views import (
    HealthCheckView,
    BuildingListView,
    BuildingDetailView,
    BuildingSummaryAPIView,
    BuildingMeterListView,
    MeterDetailView,
    BuildingReadingHistoryView,
)

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('buildings/', BuildingListView.as_view(), name='building-list'),
    path('buildings/<int:pk>/', BuildingDetailView.as_view(), name='building-detail'),
    path('buildings/<int:building_id>/summary/', BuildingSummaryAPIView.as_view(), name='building-summary'),
    path('buildings/<int:building_id>/meters/', BuildingMeterListView.as_view(), name='building-meter-list'),
    path('meters/<int:pk>/', MeterDetailView.as_view(), name='meter-detail'),
    path('buildings/<int:building_id>/readings/', BuildingReadingHistoryView.as_view(), name='building-readings'),
]

