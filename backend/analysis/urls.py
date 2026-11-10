from django.urls import path
from .views import (
    TariffPlanListCreateView,
    TariffPlanDetailView,
    EnergyAlertListView,
    EnergyAlertDetectView,
    EnergyAlertDetailView,
    BuildingCostAnalysisAPIView
)

urlpatterns = [
    path('tariffs/', TariffPlanListCreateView.as_view(), name='tariff-list'),
    path('tariffs/<int:pk>/', TariffPlanDetailView.as_view(), name='tariff-detail'),
    path('alerts/', EnergyAlertListView.as_view(), name='alert-list'),
    path('alerts/detect/', EnergyAlertDetectView.as_view(), name='alert-detect'),
    path('alerts/<int:pk>/', EnergyAlertDetailView.as_view(), name='alert-detail'),
    path('buildings/<int:building_id>/cost/', BuildingCostAnalysisAPIView.as_view(), name='building-cost-analysis'),
]

