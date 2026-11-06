from django.urls import path
from .views import (
    BuildingListView,
    BuildingDetailView,
    BuildingSummaryAPIView
)

urlpatterns = [
    path('buildings/', BuildingListView.as_view(), name='building-list'),
    path('buildings/<int:pk>/', BuildingDetailView.as_view(), name='building-detail'),
    path('buildings/<int:building_id>/summary/', BuildingSummaryAPIView.as_view(), name='building-summary'),
]

