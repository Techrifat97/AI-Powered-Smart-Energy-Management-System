from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from monitoring.models import Building, Meter, EnergyReading
from coach.models import AIRecommendation, LLMRequestLog


class CoachAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.building = Building.objects.create(
            name="Test Engineering Lab",
            location="Room E101",
            area_sqm=2000.0,
            baseline_kwh_per_day=300.0
        )
        self.meter = Meter.objects.create(
            building=self.building,
            device_id="TEST-ENG-01",
            meter_type="ELECTRICITY"
        )
        now = timezone.now()
        EnergyReading.objects.create(
            meter=self.meter,
            timestamp=now,
            energy_kwh=120.0,
            power_kw=35.0
        )

    def test_forecast_endpoint(self):
        url = reverse('building-forecast', kwargs={'building_id': self.building.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['building_id'], self.building.id)
        self.assertEqual(response.data['horizon_days'], 7)
        self.assertEqual(len(response.data['forecast']), 7)
        self.assertIn('predicted_kwh', response.data['forecast'][0])

    def test_recommendation_generate_endpoint(self):
        url = reverse('recommendations-generate')
        payload = {
            'building_id': self.building.id,
            'target_savings_pct': 15.0
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('recommendations', response.data)
        self.assertGreaterEqual(len(response.data['recommendations']), 1)
        self.assertIn('sustainability_assessment', response.data)
        self.assertIn('engine_telemetry', response.data)
        self.assertIn('sustainability_score', response.data['sustainability_assessment'])
        self.assertTrue(AIRecommendation.objects.filter(building=self.building).exists())
        self.assertTrue(LLMRequestLog.objects.exists())
