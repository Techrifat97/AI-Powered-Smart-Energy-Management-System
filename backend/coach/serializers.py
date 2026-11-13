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


class RecommendationFeedbackSerializer(serializers.ModelSerializer):
    recommendation = serializers.PrimaryKeyRelatedField(
        queryset=AIRecommendation.objects.all(),
        required=False,
    )
    user_username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = RecommendationFeedback
        fields = ['id', 'recommendation', 'user', 'user_username', 'rating', 'is_accepted', 'comment', 'created_at']
        read_only_fields = ['user']

    def validate(self, attrs):
        url_recommendation = self.context.get('recommendation')
        body_recommendation = attrs.get('recommendation')
        if url_recommendation is not None:
            if body_recommendation is not None and body_recommendation.pk != url_recommendation.pk:
                raise serializers.ValidationError({
                    'recommendation': 'Recommendation ID in body must match the recommendation ID in the URL.'
                })
            attrs['recommendation'] = url_recommendation
        elif body_recommendation is None:
            raise serializers.ValidationError({
                'recommendation': 'This field is required.'
            })

        request = self.context.get('request')
        user = getattr(request, 'user', None)
        recommendation = attrs.get('recommendation')
        if user is not None and user.is_authenticated and recommendation is not None:
            if RecommendationFeedback.objects.filter(recommendation=recommendation, user=user).exists():
                raise serializers.ValidationError({
                    'detail': 'You have already submitted feedback for this recommendation.'
                })
        return attrs


class AIRecommendationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    feedback = RecommendationFeedbackSerializer(many=True, read_only=True)

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
            'feedback',
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

