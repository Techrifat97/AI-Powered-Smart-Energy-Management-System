from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from monitoring.models import Building, Meter, EnergyReading
from django.utils import timezone


class MonitoringAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.building = Building.objects.create(
            name="Test Science Hall",
            location="Building 4",
            area_sqm=1200.0,
            baseline_kwh_per_day=150.0
        )
        self.meter = Meter.objects.create(
            building=self.building,
            device_id="TEST-MTR-01",
            meter_type="ELECTRICITY"
        )
        now = timezone.now()
        EnergyReading.objects.create(
            meter=self.meter,
            timestamp=now,
            energy_kwh=45.5,
            power_kw=12.2
        )

    def test_building_summary_endpoint(self):
        url = reverse('building-summary', kwargs={'building_id': self.building.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['building_id'], self.building.id)
        self.assertEqual(response.data['total_consumption_kwh'], 45.5)
        self.assertEqual(response.data['peak_demand_kw'], 12.2)
