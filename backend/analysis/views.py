from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Sum

from monitoring.models import Building, EnergyReading
from .models import TariffPlan, EnergyAlert, CostReport
from .serializers import TariffPlanSerializer, EnergyAlertSerializer, CostReportSerializer


class TariffPlanListCreateView(ListCreateAPIView):
    """
    List and create electricity tariff pricing structures.
    """
    queryset = TariffPlan.objects.all()
    serializer_class = TariffPlanSerializer


class EnergyAlertListView(ListAPIView):
    """
    List anomaly and threshold alerts, optionally filtered by building.
    """
    serializer_class = EnergyAlertSerializer

    def get_queryset(self):
        queryset = EnergyAlert.objects.all()
        building_id = self.request.query_params.get('building_id')
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        return queryset


class EnergyAlertDetailView(RetrieveUpdateAPIView):
    """
    Retrieve and acknowledge/resolve an energy alert.
    """
    queryset = EnergyAlert.objects.all()
    serializer_class = EnergyAlertSerializer


class BuildingCostAnalysisAPIView(APIView):
    """
    Subsystem 3 (Analysis): Compute electricity cost breakdown for a building.
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        tariff = TariffPlan.objects.filter(is_active=True).first()

        rate_std = tariff.rate_standard_eur_per_kwh if tariff else 0.32
        solar_credit = tariff.solar_feed_in_eur_per_kwh if tariff else 0.08

        elec_kwh = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type__in=['ELECTRICITY', 'HVAC', 'LIGHTING']
        ).aggregate(total=Sum('energy_kwh'))['total'] or 0.0

        solar_kwh = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type='SOLAR'
        ).aggregate(total=Sum('energy_kwh'))['total'] or 0.0

        net_grid_kwh = max(0.0, elec_kwh - solar_kwh)
        gross_cost_eur = round(elec_kwh * rate_std, 2)
        solar_savings_eur = round(solar_kwh * rate_std, 2)
        net_cost_eur = round(net_grid_kwh * rate_std, 2)

        return Response({
            'building_id': building.id,
            'building_name': building.name,
            'tariff_applied': tariff.name if tariff else 'Default Standard Tariff',
            'rate_eur_per_kwh': rate_std,
            'total_consumption_kwh': round(elec_kwh, 2),
            'solar_generated_kwh': round(solar_kwh, 2),
            'gross_cost_eur': gross_cost_eur,
            'solar_savings_eur': solar_savings_eur,
            'net_cost_eur': net_cost_eur
        }, status=status.HTTP_200_OK)

