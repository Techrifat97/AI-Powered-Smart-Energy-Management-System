from rest_framework import serializers
from .models import Building, Meter, EnergyReading


class MeterSerializer(serializers.ModelSerializer):
    meter_type_display = serializers.CharField(source='get_meter_type_display', read_only=True)

    class Meta:
        model = Meter
        fields = ['id', 'device_id', 'meter_type', 'meter_type_display', 'unit', 'is_active', 'created_at']


class BuildingSerializer(serializers.ModelSerializer):
    meters = MeterSerializer(many=True, read_only=True)

    class Meta:
        model = Building
        fields = ['id', 'name', 'location', 'area_sqm', 'baseline_kwh_per_day', 'meters', 'created_at']


class EnergyReadingSerializer(serializers.ModelSerializer):
    meter_device_id = serializers.CharField(source='meter.device_id', read_only=True)

    class Meta:
        model = EnergyReading
        fields = ['id', 'meter', 'meter_device_id', 'timestamp', 'energy_kwh', 'power_kw', 'voltage']


class BuildingSummarySerializer(serializers.Serializer):
    building_id = serializers.IntegerField()
    building_name = serializers.CharField()
    location = serializers.CharField()
    area_sqm = serializers.FloatField()
    baseline_kwh_per_day = serializers.FloatField()
    total_consumption_kwh = serializers.FloatField()
    average_daily_kwh = serializers.FloatField()
    peak_demand_kw = serializers.FloatField()
    total_solar_generated_kwh = serializers.FloatField()
    net_grid_consumption_kwh = serializers.FloatField()
    active_meters_count = serializers.IntegerField()
    total_readings_count = serializers.IntegerField()
    earliest_reading = serializers.DateTimeField(allow_null=True)
    latest_reading = serializers.DateTimeField(allow_null=True)

