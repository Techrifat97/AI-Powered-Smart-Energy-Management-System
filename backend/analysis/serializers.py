from rest_framework import serializers
from .models import TariffPlan, EnergyAlert, CostReport


class TariffPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffPlan
        fields = [
            'id', 'name', 'rate_standard_eur_per_kwh', 'rate_peak_eur_per_kwh',
            'peak_start_hour', 'peak_end_hour', 'solar_feed_in_eur_per_kwh',
            'is_active', 'created_at'
        ]


class EnergyAlertSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)
    building_name = serializers.CharField(source='building.name', read_only=True)

    class Meta:
        model = EnergyAlert
        fields = [
            'id', 'building', 'building_name', 'meter', 'severity',
            'severity_display', 'alert_type', 'alert_type_display',
            'message', 'value_recorded', 'threshold_value', 'is_resolved', 'created_at'
        ]


class CostReportSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)

    class Meta:
        model = CostReport
        fields = [
            'id', 'building', 'building_name', 'tariff', 'period_start',
            'period_end', 'total_grid_kwh', 'total_cost_eur', 'solar_savings_eur', 'created_at'
        ]

