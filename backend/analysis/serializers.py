from math import isfinite

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
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        def value(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name) if self.instance else TariffPlan._meta.get_field(name).default

        for name in ('rate_standard_eur_per_kwh', 'rate_peak_eur_per_kwh', 'solar_feed_in_eur_per_kwh'):
            rate = value(name)
            if not isfinite(rate) or rate < 0:
                raise serializers.ValidationError({name: 'Must be a finite, non-negative number.'})
        for name in ('peak_start_hour', 'peak_end_hour'):
            if not 0 <= value(name) <= 23:
                raise serializers.ValidationError({name: 'Must be an hour between 0 and 23.'})
        if value('peak_start_hour') == value('peak_end_hour'):
            raise serializers.ValidationError({'peak_end_hour': 'Must differ from peak_start_hour.'})
        if value('is_active'):
            others = TariffPlan.objects.filter(is_active=True)
            if self.instance:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError(
                    {'is_active': 'Another tariff is already active; deactivate it first.'})
        return attrs


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
        # Alerts are produced by detection; clients may only resolve/reopen them.
        read_only_fields = [f for f in fields if f != 'is_resolved']


class CostReportSerializer(serializers.ModelSerializer):
    building_name = serializers.CharField(source='building.name', read_only=True)

    class Meta:
        model = CostReport
        fields = [
            'id', 'building', 'building_name', 'tariff', 'period_start',
            'period_end', 'total_grid_kwh', 'total_cost_eur', 'solar_savings_eur', 'created_at'
        ]



class ScenarioTariffSerializer(serializers.Serializer):
    """Alternative tariff for a what-if scenario; never stored."""
    name = serializers.CharField(max_length=100, default='Scenario tariff')
    rate_standard_eur_per_kwh = serializers.FloatField(min_value=0)
    rate_peak_eur_per_kwh = serializers.FloatField(min_value=0)
    peak_start_hour = serializers.IntegerField(min_value=0, max_value=23, default=11)
    peak_end_hour = serializers.IntegerField(min_value=0, max_value=23, default=16)
    solar_feed_in_eur_per_kwh = serializers.FloatField(min_value=0, default=0.0)

    def validate(self, attrs):
        for name in ('rate_standard_eur_per_kwh', 'rate_peak_eur_per_kwh', 'solar_feed_in_eur_per_kwh'):
            if not isfinite(attrs[name]):
                raise serializers.ValidationError({name: 'Must be finite.'})
        if attrs['peak_start_hour'] == attrs['peak_end_hour']:
            raise serializers.ValidationError({'peak_end_hour': 'Must differ from peak_start_hour.'})
        return attrs


class ScenarioRequestSerializer(serializers.Serializer):
    tariff = ScenarioTariffSerializer(required=False)
    consumption_change_pct = serializers.FloatField(default=0.0, min_value=-100, max_value=1000)
    solar_change_pct = serializers.FloatField(default=0.0, min_value=-100, max_value=1000)


class CostReportRequestSerializer(serializers.Serializer):
    period_start = serializers.DateField()
    period_end = serializers.DateField()
