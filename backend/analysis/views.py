from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from monitoring.models import Building
from .services.costs import cost_analysis
from .models import TariffPlan, EnergyAlert, CostReport
from .serializers import TariffPlanSerializer, EnergyAlertSerializer, CostReportSerializer


class TariffPlanListCreateView(ListCreateAPIView):
    """
    List and create electricity tariff pricing structures.
    """
    queryset = TariffPlan.objects.all()
    serializer_class = TariffPlanSerializer


class TariffPlanDetailView(RetrieveUpdateAPIView):
    """
    Retrieve or update one tariff, e.g. to deactivate it before activating another.
    """
    queryset = TariffPlan.objects.all()
    serializer_class = TariffPlanSerializer


class EnergyAlertListView(ListAPIView):
    """
    List stored alerts, optionally filtered by building; no detection runs here.
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
    Retrieve or update stored alert fields.
    """
    queryset = EnergyAlert.objects.all()
    serializer_class = EnergyAlertSerializer


class BuildingCostAnalysisAPIView(APIView):
    """
    Return tariff scenario estimates from shared S1 intervals; not a utility bill.
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        return Response(cost_analysis(building), status=status.HTTP_200_OK)
