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



class TariffValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def payload(self, **overrides):
        data = {'name': 'Flat', 'rate_standard_eur_per_kwh': 0.3, 'rate_peak_eur_per_kwh': 0.3,
                'peak_start_hour': 11, 'peak_end_hour': 16, 'solar_feed_in_eur_per_kwh': 0.08,
                'is_active': True}
        data.update(overrides)
        return data

    def test_valid_tariff_is_created(self):
        response = self.client.post(reverse('tariff-list'), self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_values_are_rejected(self):
        for overrides in [{'rate_standard_eur_per_kwh': -1}, {'peak_start_hour': 24},
                          {'peak_start_hour': 5, 'peak_end_hour': 5}]:
            with self.subTest(overrides=overrides):
                response = self.client.post(reverse('tariff-list'), self.payload(**overrides), format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TariffPlan.objects.count(), 0)

    def test_second_active_tariff_is_rejected_until_first_is_deactivated(self):
        first = self.client.post(reverse('tariff-list'), self.payload(), format='json').data
        response = self.client.post(reverse('tariff-list'), self.payload(name='Second'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(reverse('tariff-detail', args=[first['id']]),
                                     {'is_active': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(reverse('tariff-list'), self.payload(name='Second'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_patch_keeps_active_tariff_valid(self):
        first = self.client.post(reverse('tariff-list'), self.payload(), format='json').data
        response = self.client.patch(reverse('tariff-detail', args=[first['id']]),
                                     {'rate_standard_eur_per_kwh': 0.4}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.patch(reverse('tariff-detail', args=[first['id']]),
                                     {'peak_end_hour': 11}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
