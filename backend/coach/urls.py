from django.urls import path
from .views import (
    BuildingForecastAPIView,
    GenerateRecommendationsAPIView,
    RecommendationListView,
    RecommendationFeedbackCreateView
)

urlpatterns = [
    path('buildings/<int:building_id>/forecast/', BuildingForecastAPIView.as_view(), name='building-forecast'),
    path('recommendations/generate/', GenerateRecommendationsAPIView.as_view(), name='recommendations-generate'),
    path('recommendations/', RecommendationListView.as_view(), name='recommendation-list'),
    path('recommendations/<int:pk>/feedback/', RecommendationFeedbackCreateView.as_view(), name='recommendation-feedback'),
]

