from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from monitoring.models import Building
from .services.alerts import detect_alerts
from .services.costs import cost_analysis
from .services.reports import ReportUnavailable, generate_cost_report
from .services.scenarios import run_scenario
from .models import TariffPlan, EnergyAlert, CostReport
from .serializers import (
    TariffPlanSerializer, EnergyAlertSerializer, CostReportSerializer,
    ScenarioRequestSerializer, CostReportRequestSerializer,
)


class TariffPlanListCreateView(ListCreateAPIView):
    """
    List and create electricity tariff pricing structures.
    """
    queryset = TariffPlan.objects.all()
    serializer_class = TariffPlanSerializer
    permission_classes = [IsAuthenticated]


class TariffPlanDetailView(RetrieveUpdateAPIView):
    """
    Retrieve or update one tariff, e.g. to deactivate it before activating another.
    """
    queryset = TariffPlan.objects.all()
    serializer_class = TariffPlanSerializer
    permission_classes = [IsAuthenticated]


class EnergyAlertListView(ListAPIView):
    """
    List stored alerts, optionally filtered by building; no detection runs here.
    """
    serializer_class = EnergyAlertSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]


class BuildingCostAnalysisAPIView(APIView):
    """
    Return tariff scenario estimates from shared S1 intervals; not a utility bill.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        return Response(cost_analysis(building), status=status.HTTP_200_OK)


class BuildingScenarioAPIView(APIView):
    """
    Re-price recorded history under an alternative tariff, consumption or solar change.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        serializer = ScenarioRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tariff = TariffPlan(**data['tariff']) if 'tariff' in data else None
        return Response(run_scenario(
            building, tariff=tariff, consumption_change_pct=data['consumption_change_pct'],
            solar_change_pct=data['solar_change_pct'],
            period_start=data.get('period_start'), period_end=data.get('period_end')), status=status.HTTP_200_OK)


class BuildingCostReportView(APIView):
    """
    GET stored cost reports of a building; POST generates one for an inclusive UTC date range.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, building_id):
        get_object_or_404(Building, id=building_id)
        reports = CostReport.objects.filter(building_id=building_id)
        return Response(CostReportSerializer(reports, many=True).data)

    def post(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)
        serializer = CostReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = generate_cost_report(building, **serializer.validated_data)
        except ReportUnavailable as error:
            return Response({'available': False, 'reason': error.reason},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(CostReportSerializer(report).data, status=status.HTTP_201_CREATED)


class CostReportListView(ListAPIView):
    """
    List stored cost reports, optionally filtered by building.
    """
    serializer_class = CostReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = CostReport.objects.all()
        building_id = self.request.query_params.get('building_id')
        return queryset.filter(building_id=building_id) if building_id else queryset
