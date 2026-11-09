from collections.abc import Mapping

from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from .models import Building, Meter, EnergyReading
from .services.inventory import save_building, save_meter


def _model_write(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ModelValidationError as error:
        detail = error.message_dict if hasattr(error, 'error_dict') else {'non_field_errors': error.messages}
        if '__all__' in detail:
            detail['non_field_errors'] = detail.pop('__all__')
        raise serializers.ValidationError(detail) from None


class WritableFieldsMixin:
    update_writable_fields = None

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            allowed = {name for name, field in self.fields.items() if not field.read_only}
            if self.instance is not None and self.update_writable_fields is not None:
                allowed = self.update_writable_fields
            errors = {name: ['This field cannot be set through this endpoint.']
                      for name in data if name not in allowed}
            if errors:
                raise serializers.ValidationError(errors)
            # Use mapping semantics for form data too: an omitted HTML checkbox
            # must not silently become an explicit solar=False or active=False.
            data = dict(data.items())
        return super().to_internal_value(data)


class MeterSerializer(WritableFieldsMixin, serializers.ModelSerializer):
    update_writable_fields = {'is_active'}
    meter_type_display = serializers.CharField(source='get_meter_type_display', read_only=True)

    class Meta:
        model = Meter
        fields = ['id', 'building', 'device_id', 'meter_type', 'meter_type_display', 'unit', 'is_active', 'created_at']
        read_only_fields = ['id', 'building', 'created_at']

    def validate(self, attributes):
        if self.instance is not None and 'is_active' not in attributes:
            raise serializers.ValidationError({'is_active': 'Provide true or false.'})
        return attributes

    def create(self, validated_data):
        return _model_write(save_meter, validated_data, building_id=self.context['building_id'])

    def update(self, instance, validated_data):
        return _model_write(save_meter, validated_data, building_id=instance.building_id, meter_id=instance.pk)


class BuildingSerializer(WritableFieldsMixin, serializers.ModelSerializer):
    meters = MeterSerializer(many=True, read_only=True)
    has_solar_installation = serializers.BooleanField(required=False, allow_null=False)

    class Meta:
        model = Building
        fields = ['id', 'name', 'location', 'area_sqm', 'baseline_kwh_per_day', 'has_solar_installation', 'meters', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attributes):
        if self.instance is None and 'has_solar_installation' not in attributes:
            raise serializers.ValidationError({'has_solar_installation': 'Explicitly provide true or false.'})
        return attributes

    def create(self, validated_data):
        return _model_write(save_building, validated_data)

    def update(self, instance, validated_data):
        return _model_write(save_building, validated_data, building_id=instance.pk)


class EnergyReadingSerializer(serializers.ModelSerializer):
    meter_device_id = serializers.CharField(source='meter.device_id', read_only=True)
    meter_type = serializers.CharField(source='meter.meter_type', read_only=True)
    meter_unit = serializers.CharField(source='meter.unit', read_only=True)

    class Meta:
        model = EnergyReading
        fields = ['id', 'meter', 'meter_device_id', 'meter_type', 'meter_unit',
                  'timestamp', 'interval_seconds', 'energy_kwh', 'power_kw', 'voltage']
        read_only_fields = fields


class ReadingHistoryQuerySerializer(serializers.Serializer):
    meter_id = serializers.IntegerField(required=False, min_value=1)
    start = serializers.CharField(required=False)
    end = serializers.CharField(required=False)

    def _aware_bound(self, value):
        try:
            parsed = parse_datetime(value)
        except (ValueError, TypeError):
            parsed = None
        if parsed is None or timezone.is_naive(parsed):
            raise serializers.ValidationError('Use an ISO 8601 datetime with Z or an explicit UTC offset.')
        return parsed

    def validate_start(self, value):
        return self._aware_bound(value)

    def validate_end(self, value):
        return self._aware_bound(value)

    def validate(self, attributes):
        if 'start' in attributes and 'end' in attributes and attributes['start'] >= attributes['end']:
            raise serializers.ValidationError({'end': 'End must be after start.'})
        return attributes


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
