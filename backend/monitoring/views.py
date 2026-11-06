from datetime import timedelta
from django.db.models import Sum, Max, Min, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import Building, Meter, EnergyReading
from .serializers import (
    BuildingSerializer,
    BuildingSummarySerializer,
    EnergyReadingSerializer
)


class BuildingListView(ListAPIView):
    """
    List all monitored buildings.
    """
    queryset = Building.objects.all().prefetch_related('meters')
    serializer_class = BuildingSerializer


class BuildingDetailView(RetrieveAPIView):
    """
    Retrieve details for a single building including its installed meters.
    """
    queryset = Building.objects.all().prefetch_related('meters')
    serializer_class = BuildingSerializer


class BuildingSummaryAPIView(APIView):
    """
    Endpoint 1: Subsystem 1 (Monitoring) Aggregation Summary.
    Computes aggregated consumption, peak demand, and solar generation for a building.
    This serves as the primary data payload consumed by Subsystem 2 (Coach/Forecasting).
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)

        # Separate electricity consumers and solar generation
        electricity_readings = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type__in=['ELECTRICITY', 'HVAC', 'LIGHTING']
        )
        solar_readings = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type='SOLAR'
        )

        elec_stats = electricity_readings.aggregate(
            total_kwh=Sum('energy_kwh'),
            peak_kw=Max('power_kw'),
            earliest=Min('timestamp'),
            latest=Max('timestamp'),
            count=Count('id')
        )
        solar_stats = solar_readings.aggregate(
            solar_kwh=Sum('energy_kwh')
        )

        total_consumption = round(elec_stats['total_kwh'] or 0.0, 2)
        total_solar = round(solar_stats['solar_kwh'] or 0.0, 2)
        peak_demand = round(elec_stats['peak_kw'] or 0.0, 2)
        net_grid = round(max(0.0, total_consumption - total_solar), 2)

        earliest = elec_stats['earliest']
        latest = elec_stats['latest']
        days = 1
        if earliest and latest:
            diff = (latest - earliest).total_seconds() / 86400.0
            days = max(1.0, round(diff, 1))

        avg_daily = round(total_consumption / days, 2) if total_consumption > 0 else building.baseline_kwh_per_day

        data = {
            'building_id': building.id,
            'building_name': building.name,
            'location': building.location,
            'area_sqm': building.area_sqm,
            'baseline_kwh_per_day': building.baseline_kwh_per_day,
            'total_consumption_kwh': total_consumption,
            'average_daily_kwh': avg_daily,
            'peak_demand_kw': peak_demand,
            'total_solar_generated_kwh': total_solar,
            'net_grid_consumption_kwh': net_grid,
            'active_meters_count': building.meters.filter(is_active=True).count(),
            'total_readings_count': (elec_stats['count'] or 0) + (solar_readings.count()),
            'earliest_reading': earliest,
            'latest_reading': latest,
        }

        serializer = BuildingSummarySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
