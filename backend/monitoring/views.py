from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from .models import Building
from .services.aggregation import summarize_building
from .serializers import (
    BuildingSerializer,
    BuildingSummarySerializer,
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
    Summarize all stored history, including readings from inactive meters.
    Missing or ambiguous main data is flagged; it is not replaced by a baseline.
    The shared function also supports time windows for future Python consumers;
    this endpoint retains its existing all-history scope and URL.
    """

    def get(self, request, building_id):
        building = get_object_or_404(Building, id=building_id)

        data = summarize_building(building)
        serializer = BuildingSummarySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
