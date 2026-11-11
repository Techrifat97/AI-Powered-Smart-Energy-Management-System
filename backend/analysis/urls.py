from django.urls import path
from .views import (
    TariffPlanListCreateView,
    TariffPlanDetailView,
    EnergyAlertListView,
    EnergyAlertDetectView,
    EnergyAlertDetailView,
    BuildingCostAnalysisAPIView,
    BuildingScenarioAPIView,
    BuildingCostReportView,
    CostReportListView,
)

urlpatterns = [
    path('tariffs/', TariffPlanListCreateView.as_view(), name='tariff-list'),
    path('tariffs/<int:pk>/', TariffPlanDetailView.as_view(), name='tariff-detail'),
    path('alerts/', EnergyAlertListView.as_view(), name='alert-list'),
    path('alerts/detect/', EnergyAlertDetectView.as_view(), name='alert-detect'),
    path('alerts/<int:pk>/', EnergyAlertDetailView.as_view(), name='alert-detail'),
    path('buildings/<int:building_id>/cost/', BuildingCostAnalysisAPIView.as_view(), name='building-cost-analysis'),
    path('buildings/<int:building_id>/scenarios/', BuildingScenarioAPIView.as_view(), name='building-scenario'),
    path('buildings/<int:building_id>/reports/', BuildingCostReportView.as_view(), name='building-cost-reports'),
    path('reports/', CostReportListView.as_view(), name='cost-report-list'),
]

