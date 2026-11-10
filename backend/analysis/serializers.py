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

