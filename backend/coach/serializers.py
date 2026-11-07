from rest_framework import serializers
from .models import ConsumptionForecast, AIRecommendation, LLMRequestLog, RecommendationFeedback


class ConsumptionForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumptionForecast
        fields = [
            'id',
            'building',
            'forecast_date',
            'predicted_kwh',
            'confidence_lower_kwh',
            'confidence_upper_kwh',
            'trend',
            'created_at'
        ]


class AIRecommendationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = AIRecommendation
        fields = [
            'id',
            'building',
            'title',
            'category',
            'category_display',
            'priority',
            'priority_display',
            'suggested_action',
            'estimated_savings_kwh',
            'estimated_savings_eur',
            'confidence_score',
            'source',
            'status',
            'created_at'
        ]


class LLMRequestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMRequestLog
        fields = [
            'id',
            'model_name',
            'prompt_tokens',
            'completion_tokens',
            'total_tokens',
            'latency_ms',
            'status',
            'created_at'
        ]


class GenerateRecommendationInputSerializer(serializers.Serializer):
    building_id = serializers.IntegerField(required=True)
    target_savings_pct = serializers.FloatField(required=False, default=15.0, min_value=1.0, max_value=50.0)


class RecommendationFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationFeedback
        fields = ['id', 'recommendation', 'user', 'rating', 'is_accepted', 'comment', 'created_at']

