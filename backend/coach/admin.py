from django.contrib import admin
from .models import ConsumptionForecast, AIRecommendation, LLMRequestLog, RecommendationFeedback


@admin.register(ConsumptionForecast)
class ConsumptionForecastAdmin(admin.ModelAdmin):
    list_display = ('id', 'building', 'forecast_date', 'predicted_kwh', 'confidence_lower_kwh', 'confidence_upper_kwh', 'trend')
    list_filter = ('trend', 'building')
    date_hierarchy = 'forecast_date'


@admin.register(AIRecommendation)
class AIRecommendationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'building', 'category', 'priority', 'estimated_savings_kwh', 'estimated_savings_eur', 'source', 'status')
    list_filter = ('category', 'priority', 'status', 'source')
    search_fields = ('title', 'suggested_action')


@admin.register(LLMRequestLog)
class LLMRequestLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'model_name', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'latency_ms', 'status', 'created_at')
    list_filter = ('status', 'model_name')


@admin.register(RecommendationFeedback)
class RecommendationFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'recommendation', 'user', 'rating', 'is_accepted', 'created_at')
    list_filter = ('rating', 'is_accepted')
