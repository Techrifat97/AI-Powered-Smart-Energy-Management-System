from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, CreateAPIView
from rest_framework.response import Response

from monitoring.models import Building, EnergyReading
from coach.models import ConsumptionForecast, AIRecommendation, RecommendationFeedback
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
    Endpoint 2: Subsystem 2 (Forecasting & Prediction).
    Consumes S1 historical telemetry data and generates a 7-day ahead
    consumption forecast with confidence intervals and trend indicators.
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        forecaster = ConsumptionForecaster(horizon_days=7)
        forecast_data = forecaster.generate_forecast(building)

        total_predicted = round(sum(d['predicted_kwh'] for d in forecast_data), 2)
        avg_predicted = round(total_predicted / len(forecast_data), 2) if forecast_data else 0.0

        return Response({
            'building_id': building.id,
            'building_name': building.name,
            'horizon_days': 7,
            'total_predicted_7d_kwh': total_predicted,
            'avg_daily_predicted_kwh': avg_predicted,
            'forecast': forecast_data
        }, status=status.HTTP_200_OK)

    def post(self, request, building_id):
        return self.get(request, building_id)


class GenerateRecommendationsAPIView(APIView):
    """
    Endpoint 3: Subsystem 2 (AI Sustainability Coach).
    Orchestrates the entire intelligence pipeline:
    1. Extracts S1 aggregated telemetry summary for the building.
    2. Runs S2 ConsumptionForecaster to project next week's energy pattern.
    3. Evaluates sustainability score, carbon footprint, and energy grade.
    4. Invokes OpenAI (gpt-4o-mini using OPENAI_API_KEY from .env) or Rule-Based Fallback.
    5. Persists and returns actionable recommendations with cost and kWh savings.
    """

    def post(self, request):
        input_serializer = GenerateRecommendationInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        building_id = input_serializer.validated_data['building_id']
        target_savings_pct = input_serializer.validated_data.get('target_savings_pct', 15.0)

        building = get_object_or_404(Building, id=building_id)

        # 1. Fetch S1 telemetry summary directly
        electricity_readings = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type__in=['ELECTRICITY', 'HVAC', 'LIGHTING']
        )
        solar_readings = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type='SOLAR'
        )

        from django.db.models import Sum, Max, Min
        elec_agg = electricity_readings.aggregate(
            total=Sum('energy_kwh'),
            peak=Max('power_kw'),
            earliest=Min('timestamp'),
            latest=Max('timestamp')
        )
        solar_total = solar_readings.aggregate(total=Sum('energy_kwh'))['total'] or 0.0

        total_kwh = elec_agg['total'] or 0.0
        peak_kw = elec_agg['peak'] or 0.0
        earliest = elec_agg['earliest']
        latest = elec_agg['latest']

        days = 1.0
        if earliest and latest:
            diff_days = (latest - earliest).total_seconds() / 86400.0
            days = max(1.0, round(diff_days, 1))

        avg_daily_kwh = total_kwh / days if total_kwh > 0 else building.baseline_kwh_per_day
        solar_daily_kwh = solar_total / days if solar_total > 0 else 0.0

        summary = {
            'total_consumption_kwh': round(total_kwh, 2),
            'average_daily_kwh': round(avg_daily_kwh, 2),
            'peak_demand_kw': round(peak_kw, 2),
            'total_solar_generated_kwh': round(solar_total, 2),
        }

        # 2. Run S2 7-day forecast
        forecaster = ConsumptionForecaster(horizon_days=7)
        forecast_list = forecaster.generate_forecast(building)

        # 3. Compute Sustainability Score
        sustainability_assessment = SustainabilityScorer.evaluate(
            current_daily_kwh=avg_daily_kwh,
            baseline_daily_kwh=building.baseline_kwh_per_day,
            solar_daily_kwh=solar_daily_kwh
        )

        # 4. Generate AI Recommendations (OpenAI / Rule-Based)
        coach_result = SustainabilityCoachService.generate_recommendations(
            building=building,
            summary=summary,
            forecast=forecast_list,
            target_savings_pct=target_savings_pct
        )

        # 5. Serialize saved recommendation objects
        rec_serializer = AIRecommendationSerializer(coach_result['recommendations'], many=True)

        return Response({
            'building': {
                'id': building.id,
                'name': building.name,
                'location': building.location,
                'baseline_kwh_per_day': building.baseline_kwh_per_day
            },
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

    def get_queryset(self):
        queryset = AIRecommendation.objects.all()
        building_id = self.request.query_params.get('building_id')
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        return queryset


class RecommendationFeedbackCreateView(CreateAPIView):
    """
    Submit user feedback on a recommendation (thumbs up / rating / accept).
    """
    queryset = RecommendationFeedback.objects.all()
    serializer_class = RecommendationFeedbackSerializer
