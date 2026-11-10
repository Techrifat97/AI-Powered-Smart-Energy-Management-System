from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from monitoring.models import Building
from .services.alerts import detect_alerts
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
        for param, field in [('is_resolved', 'is_resolved'), ('severity', 'severity'),
                             ('alert_type', 'alert_type')]:
            value = self.request.query_params.get(param)
            if value is not None:
                if param == 'is_resolved':
                    value = value.lower() in ('1', 'true', 'yes')
                queryset = queryset.filter(**{field: value})
        return queryset


class EnergyAlertDetectView(APIView):
    """
    Run rule-based detection for a building and store newly found alerts.
    """

    def post(self, request):
        try:
            building_id = int(request.data.get('building_id'))
        except (TypeError, ValueError):
            return Response({'building_id': 'A valid building id is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        building = get_object_or_404(Building, id=building_id)
        created = detect_alerts(building)
        return Response({'building_id': building.pk, 'created_count': len(created),
                         'alerts': EnergyAlertSerializer(created, many=True).data},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


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
