from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from monitoring.models import Building, Meter, EnergyReading
from analysis.models import TariffPlan, EnergyAlert
from django.utils import timezone


class AnalysisAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.building = Building.objects.create(
            name="Test Analysis Complex",
            location="Zone B",
            area_sqm=1500.0,
            baseline_kwh_per_day=200.0
        )
        self.tariff = TariffPlan.objects.create(
            name="Standard Test Tariff",
            rate_standard_eur_per_kwh=0.30
        )

    def test_tariff_list(self):
        url = reverse('tariff-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_cost_analysis_endpoint(self):
        url = reverse('building-cost-analysis', kwargs={'building_id': self.building.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['building_id'], self.building.id)
        self.assertIn('gross_cost_eur', response.data)

