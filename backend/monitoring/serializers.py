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
        fields = ['id', 'name', 'location', 'area_sqm', 'baseline_kwh_per_day', 'has_solar_installation', 'meters', 'created_at']


class EnergyReadingSerializer(serializers.ModelSerializer):
    meter_device_id = serializers.CharField(source='meter.device_id', read_only=True)

    class Meta:
        model = EnergyReading
        fields = ['id', 'meter', 'meter_device_id', 'timestamp', 'interval_seconds', 'energy_kwh', 'power_kw', 'voltage']


class BuildingSummarySerializer(serializers.Serializer):
    building_id = serializers.IntegerField()
    building_name = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    area_sqm = serializers.FloatField()
    baseline_kwh_per_day = serializers.FloatField()
    total_consumption_kwh = serializers.FloatField(allow_null=True)
    average_daily_kwh = serializers.FloatField(
        allow_null=True, help_text='Mean recorded UTC-day total; complete coverage is not implied.'
    )
    peak_demand_kw = serializers.FloatField(
        allow_null=True, help_text='Highest recorded main-meter power sample.'
    )
    total_solar_generated_kwh = serializers.FloatField(allow_null=True)
    net_grid_consumption_kwh = serializers.FloatField(
        allow_null=True, help_text='Signed recorded gross minus solar; not actual grid imports.'
    )
    active_meters_count = serializers.IntegerField()
    total_readings_count = serializers.IntegerField()
    earliest_reading = serializers.DateTimeField(allow_null=True)
    latest_reading = serializers.DateTimeField(allow_null=True)
    main_meter_count = serializers.IntegerField()
    main_readings_count = serializers.IntegerField()
    main_data_available = serializers.BooleanField()
    main_data_ambiguous = serializers.BooleanField()
    recorded_main_days_count = serializers.IntegerField()
    solar_readings_count = serializers.IntegerField()


    main_data_reason = serializers.CharField()
    solar_data_available = serializers.BooleanField()
    solar_data_reason = serializers.CharField()
    has_solar_installation = serializers.BooleanField(allow_null=True)
    main_coverage_complete = serializers.BooleanField()
    grid_estimates_available = serializers.BooleanField()
    grid_estimates_reason = serializers.CharField()
    estimated_grid_import_kwh = serializers.FloatField(allow_null=True)
    estimated_grid_export_kwh = serializers.FloatField(allow_null=True)
    complete_main_days_count = serializers.IntegerField()
    full_day_average_kwh = serializers.FloatField(allow_null=True)
    scope_start = serializers.DateTimeField(allow_null=True)
    scope_end = serializers.DateTimeField(allow_null=True)
