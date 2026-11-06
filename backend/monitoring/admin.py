from django.contrib import admin
from .models import Building, Meter, EnergyReading


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'location', 'area_sqm', 'baseline_kwh_per_day', 'created_at')
    search_fields = ('name', 'location')


@admin.register(Meter)
class MeterAdmin(admin.ModelAdmin):
    list_display = ('id', 'device_id', 'building', 'meter_type', 'unit', 'is_active', 'created_at')
    list_filter = ('meter_type', 'is_active', 'building')
    search_fields = ('device_id', 'building__name')


@admin.register(EnergyReading)
class EnergyReadingAdmin(admin.ModelAdmin):
    list_display = ('id', 'meter', 'timestamp', 'energy_kwh', 'power_kw', 'voltage')
    list_filter = ('meter__meter_type', 'meter__building')
    date_hierarchy = 'timestamp'
