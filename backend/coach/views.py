from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from monitoring.models import Building
from monitoring.services.aggregation import summarize_building
from math import fsum
from coach.models import AIRecommendation, RecommendationFeedback
from coach.serializers import (
    ConsumptionForecastSerializer,
    AIRecommendationSerializer,
    GenerateRecommendationInputSerializer,
    RecommendationFeedbackSerializer
)
from coach.services.forecaster import ConsumptionForecaster
from coach.services.scorer import SustainabilityScorer
from coach.services.llm_coach import SustainabilityCoachService


class BuildingForecastAPIView(APIView):
    """
    Calculate and store seven daily heuristic forecasts using shared S1 data.
    Bands are illustrative; availability depends on complete UTC-day coverage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        forecaster = ConsumptionForecaster(horizon_days=7)
        forecast_data = forecaster.generate_forecast(building)

        total_predicted = round(sum(d['predicted_kwh'] for d in forecast_data), 2) if forecast_data else None
        avg_predicted = round(total_predicted / len(forecast_data), 2) if forecast_data else None

        return Response({
            'building_id': building.id,
            'building_name': building.name,
            'horizon_days': 7,
            'total_predicted_7d_kwh': total_predicted,
            'avg_daily_predicted_kwh': avg_predicted,
            'availability': forecaster.availability,
            'forecast': forecast_data
        }, status=status.HTTP_200_OK)

    def post(self, request, building_id):
        return self.get(request, building_id)


class GenerateRecommendationsAPIView(APIView):
    """
    Generate recommendations from shared S1 summaries and complete-day history.
    Sufficient observations enable the configured OpenAI or rule-based provider;
    otherwise the response reports unavailable inputs. Energy goals are
    illustrative scenarios and monetary recommendation savings are unavailable.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        input_serializer = GenerateRecommendationInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        building_id = input_serializer.validated_data['building_id']
        target_savings_pct = input_serializer.validated_data.get('target_savings_pct', 15.0)

        building = get_object_or_404(Building, id=building_id)

        # S1 owns the measurement rules. Summary remains all-history;
        # forecasting/assessment use complete days in the preceding 14 UTC days.
        summary = summarize_building(building)
        forecaster = ConsumptionForecaster(horizon_days=7)
        forecast_list = forecaster.generate_forecast(building)
        daily_rows = forecaster.history['complete_days']
        daily_average = forecaster.availability['observed_full_day_average_kwh']
        matched_days = bool(daily_rows) and all(d['import_kwh'] is not None for d in daily_rows)
        solar_daily = fsum(d['solar_kwh'] for d in daily_rows) / len(daily_rows) if matched_days else None
        import_daily = fsum(d['import_kwh'] for d in daily_rows) / len(daily_rows) if matched_days else None
        sustainability_assessment = SustainabilityScorer.evaluate(
            daily_average, building.baseline_kwh_per_day, solar_daily, import_daily_kwh=import_daily,
        )
        if not summary['main_data_available'] or not forecast_list or not matched_days:
            reason = (summary['main_data_reason'] if not summary['main_data_available'] else
                      forecaster.availability['reason'] if not forecast_list else
                      forecaster.history['summary']['grid_estimates_reason'])
            return Response({
                'building': {'id': building.id, 'name': building.name},
                'availability': {'available': False, 'reason': reason},
                'energy_summary': summary,
                'sustainability_assessment': sustainability_assessment,
                'forecast_preview': {'horizon_days': 7, 'projected_weekly_total_kwh':
                                     round(sum(d['predicted_kwh'] for d in forecast_list), 2) if forecast_list else None},
                'forecast_availability': forecaster.availability,
                'recommendations': [],
                'engine_telemetry': {'source': None, 'status': 'NOT_RUN', 'tokens_used': 0, 'latency_ms': 0},
            }, status=status.HTTP_200_OK)
        # Recommendations use observed full-day energy, never the partial-day mean.
        coach_summary = dict(summary, average_daily_kwh=daily_average,
                             total_solar_generated_kwh=solar_daily,
                             solar_scope='mean of complete observed UTC days in forecast history')

        # Invoke a provider only after measurement-availability checks pass.
        coach_result = SustainabilityCoachService.generate_recommendations(
            building=building,
            summary=coach_summary,
            forecast=forecast_list,
            target_savings_pct=target_savings_pct
        )

        rec_serializer = AIRecommendationSerializer(coach_result['recommendations'], many=True)

        return Response({
            'building': {
                'id': building.id,
                'name': building.name,
                'location': building.location,
                'baseline_kwh_per_day': building.baseline_kwh_per_day
            },
            'availability': {'available': True, 'reason': 'available'},
            'energy_summary': summary,
            'forecast_availability': forecaster.availability,
            'sustainability_assessment': sustainability_assessment,
            'forecast_preview': {
                'horizon_days': 7,
                'projected_weekly_total_kwh': round(sum(d['predicted_kwh'] for d in forecast_list), 2)
            },
            'recommendations': rec_serializer.data,
            'engine_telemetry': {
                'source': coach_result['source'],
                'status': coach_result['status'],
                'tokens_used': coach_result['tokens'],
                'latency_ms': coach_result['latency_ms']
            }
        }, status=status.HTTP_201_CREATED)


class RecommendationListView(ListAPIView):
    """
    List all generated recommendations, optionally filtered by building_id.
    """
    serializer_class = AIRecommendationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = AIRecommendation.objects.prefetch_related('feedback__user').all()
        building_id = self.request.query_params.get('building_id')
        if building_id:
            try:
                building_id = int(building_id)
            except (TypeError, ValueError):
                raise ValidationError({'building_id': 'Enter a valid integer.'})
            queryset = queryset.filter(building_id=building_id)
        return queryset


class RecommendationFeedbackCreateView(ListCreateAPIView):
    """
    List or store submitted feedback bound to the recommendation referenced in the URL.
    """
    serializer_class = RecommendationFeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        self.recommendation = get_object_or_404(AIRecommendation, pk=self.kwargs['pk'])
        return RecommendationFeedback.objects.filter(recommendation=self.recommendation).select_related('user')

    def create(self, request, *args, **kwargs):
        self.recommendation = get_object_or_404(AIRecommendation, pk=self.kwargs['pk'])
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self, 'recommendation'):
            context['recommendation'] = self.recommendation
        return context
