from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.pagination import PageNumberPagination

from .models import Building, Meter, EnergyReading
from .services.aggregation import summarize_building
from .serializers import (
    BuildingSerializer,
    BuildingSummarySerializer,
    MeterSerializer,
    EnergyReadingSerializer,
    ReadingHistoryQuerySerializer,
)


class BuildingListView(ListCreateAPIView):
    """
    List or create buildings with validated inventory metadata.
    """
    queryset = Building.objects.all().prefetch_related('meters')
    serializer_class = BuildingSerializer


class BuildingDetailView(RetrieveUpdateAPIView):
    """
    Retrieve or update building details, including nested meter information.
    """
    queryset = Building.objects.all().prefetch_related('meters')
    serializer_class = BuildingSerializer


class BuildingMeterListView(ListCreateAPIView):
    serializer_class = MeterSerializer

    def get_queryset(self):
        building = get_object_or_404(Building, pk=self.kwargs['building_id'])
        return Meter.objects.filter(building=building).order_by('pk')

    def get_serializer_context(self):
        return dict(super().get_serializer_context(), building_id=self.kwargs['building_id'])


class MeterDetailView(RetrieveUpdateAPIView):
    queryset = Meter.objects.all()
    serializer_class = MeterSerializer
    http_method_names = ['get', 'patch', 'head', 'options']


class ReadingHistoryPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500


class BuildingReadingHistoryView(ListAPIView):
    serializer_class = EnergyReadingSerializer
    pagination_class = ReadingHistoryPagination

    def get_queryset(self):
        building = get_object_or_404(Building, pk=self.kwargs['building_id'])
        # QueryDict's HTML empty-field handling would silently drop start=/end=.
        query = ReadingHistoryQuerySerializer(data=self.request.query_params.dict())
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        readings = EnergyReading.objects.filter(meter__building=building)
        if 'meter_id' in filters:
            meter = get_object_or_404(Meter, pk=filters['meter_id'], building=building)
            readings = readings.filter(meter=meter)
        if 'start' in filters:
            readings = readings.filter(timestamp__gte=filters['start'])
        if 'end' in filters:
            readings = readings.filter(timestamp__lt=filters['end'])
        return readings.select_related('meter').order_by('-timestamp', '-pk')


class BuildingSummaryAPIView(APIView):
    """
    Summarize all stored history, including readings from inactive meters.
    Missing or ambiguous main data is flagged; it is not replaced by a baseline.
    The Python service supports optional time windows; the HTTP endpoint
    summarizes all stored history.
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)

        data = summarize_building(building)
        serializer = BuildingSummarySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
