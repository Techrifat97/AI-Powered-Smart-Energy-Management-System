from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from monitoring.models import Building, Meter, EnergyReading
from analysis.models import TariffPlan, EnergyAlert, CostReport
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from analysis.services.alerts import detect_alerts


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


class AlertDetectionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.building = Building.objects.create(name='Alert lab', baseline_kwh_per_day=10.0)
        self.meter = Meter.objects.create(building=self.building, device_id='ALERT-MAIN',
                                          meter_type='ELECTRICITY')

    def add(self, start, powers, energy=0.01):
        EnergyReading.objects.bulk_create([
            EnergyReading(meter=self.meter, timestamp=start + timedelta(minutes=i),
                          interval_seconds=60, energy_kwh=energy, power_kw=p)
            for i, p in enumerate(powers)])

    def types(self, created):
        return sorted(a.alert_type for a in created)

    def test_peak_spike(self):
        start = datetime(2026, 1, 5, 12, tzinfo=dt_timezone.utc)
        self.add(start, [1.0] * 20 + [5.0])
        created = detect_alerts(self.building, now=start + timedelta(minutes=21))
        self.assertEqual(self.types(created), ['PEAK_SPIKE'])
        self.assertEqual(created[0].value_recorded, 5.0)

    def test_no_alert_for_steady_load(self):
        start = datetime(2026, 1, 5, 12, tzinfo=dt_timezone.utc)
        self.add(start, [1.0] * 21)
        self.assertEqual(detect_alerts(self.building, now=start + timedelta(minutes=21)), [])

    def test_meter_offline_and_duplicates_are_not_repeated(self):
        start = datetime(2026, 1, 5, 12, tzinfo=dt_timezone.utc)
        self.add(start, [1.0])
        now = start + timedelta(minutes=45)
        self.assertEqual(self.types(detect_alerts(self.building, now=now)), ['METER_OFFLINE'])
        self.assertEqual(detect_alerts(self.building, now=now), [])
        EnergyAlert.objects.update(is_resolved=True)
        self.assertEqual(self.types(detect_alerts(self.building, now=now)), ['METER_OFFLINE'])

    def test_unusual_night_load(self):
        day = datetime(2026, 1, 5, tzinfo=dt_timezone.utc)
        self.add(day + timedelta(hours=2), [3.0] * 12)
        self.add(day + timedelta(hours=12), [4.0] * 12)
        created = detect_alerts(self.building, now=day + timedelta(hours=12, minutes=12))
        self.assertEqual(self.types(created), ['UNUSUAL_NIGHT_LOAD'])

    def test_budget_exceeded_uses_complete_days_only(self):
        day = datetime(2026, 1, 5, tzinfo=dt_timezone.utc)
        self.add(day, [1.0] * 1439)
        now = day + timedelta(days=1, hours=1)
        self.assertNotIn('BUDGET_EXCEEDED', self.types(detect_alerts(self.building, now=now)))
        EnergyAlert.objects.all().delete()
        self.add(day + timedelta(minutes=1439), [1.0])
        self.assertIn('BUDGET_EXCEEDED', self.types(detect_alerts(self.building, now=now)))

    def test_detect_endpoint_and_validation(self):
        url = reverse('alert-detect')
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'building_id': 999}, format='json').status_code, 404)
        response = self.client.post(url, {'building_id': self.building.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created_count'], 0)

    def test_alert_update_only_changes_resolution_and_list_filters(self):
        alert = EnergyAlert.objects.create(building=self.building, message='original')
        EnergyAlert.objects.create(building=self.building, message='other', severity='CRITICAL',
                                   is_resolved=True)
        response = self.client.patch(reverse('alert-detail', args=[alert.id]),
                                     {'message': 'changed', 'severity': 'INFO', 'is_resolved': True},
                                     format='json')
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual((alert.message, alert.severity, alert.is_resolved), ('original', 'WARNING', True))
        listing = self.client.get(reverse('alert-list'), {'is_resolved': 'true', 'severity': 'CRITICAL'})
        self.assertEqual(listing.data['count'], 1)
        listing = self.client.get(reverse('alert-list'), {'is_resolved': 'false'})
        self.assertEqual(listing.data['count'], 0)


class ReportAndScenarioTests(TestCase):
    """One fully covered UTC day: 14.4 kWh consumed, 5.76 kWh solar, 8.64 kWh imported."""

    def setUp(self):
        self.client = APIClient()
        self.building = Building.objects.create(name='Report lab', baseline_kwh_per_day=100.0)
        main = Meter.objects.create(building=self.building, device_id='REP-MAIN', meter_type='ELECTRICITY')
        solar = Meter.objects.create(building=self.building, device_id='REP-SOLAR', meter_type='SOLAR')
        self.day = datetime(2026, 1, 5, tzinfo=dt_timezone.utc)
        EnergyReading.objects.bulk_create(
            [EnergyReading(meter=main, timestamp=self.day + timedelta(minutes=i),
                           interval_seconds=60, energy_kwh=0.01, power_kw=0.6) for i in range(1440)] +
            [EnergyReading(meter=solar, timestamp=self.day + timedelta(minutes=i),
                           interval_seconds=60, energy_kwh=0.004, power_kw=0.24) for i in range(1440)])

    def activate_tariff(self, rate=0.30):
        return TariffPlan.objects.create(
            name='Flat', rate_standard_eur_per_kwh=rate, rate_peak_eur_per_kwh=rate,
            peak_start_hour=11, peak_end_hour=16, solar_feed_in_eur_per_kwh=0.10, is_active=True)

    def post_report(self, start='2026-01-05', end='2026-01-05'):
        return self.client.post(reverse('building-cost-reports', args=[self.building.id]),
                                {'period_start': start, 'period_end': end}, format='json')

    def test_report_is_generated_and_listed(self):
        tariff = self.activate_tariff()
        response = self.post_report()
        self.assertEqual(response.status_code, 201)
        self.assertAlmostEqual(response.data['total_grid_kwh'], 8.64, places=6)
        self.assertAlmostEqual(response.data['total_cost_eur'], 2.59, places=2)
        self.assertAlmostEqual(response.data['solar_savings_eur'], 1.73, places=2)
        self.assertEqual(CostReport.objects.get().tariff, tariff)
        listing = self.client.get(reverse('building-cost-reports', args=[self.building.id]))
        self.assertEqual(len(listing.data), 1)
        listing = self.client.get(reverse('cost-report-list'), {'building_id': self.building.id})
        self.assertEqual(listing.data['count'], 1)

    def test_report_is_refused_without_tariff_or_full_coverage(self):
        response = self.post_report()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['reason'], 'missing_active_tariff')
        self.activate_tariff()
        response = self.post_report(end='2026-01-06')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data['reason'], 'period_not_fully_covered')
        response = self.post_report(start='2026-01-06', end='2026-01-05')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(CostReport.objects.count(), 0)

    def test_report_rejects_bad_dates(self):
        self.activate_tariff()
        self.assertEqual(self.post_report(start='not-a-date').status_code, 400)

    def scenario(self, **body):
        return self.client.post(reverse('building-scenario', args=[self.building.id]), body, format='json')

    def test_scenario_requires_active_tariff(self):
        response = self.scenario(consumption_change_pct=-10)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['available'])
        self.assertEqual(response.data['reason'], 'missing_active_tariff')

    def test_scenario_without_changes_equals_baseline(self):
        self.activate_tariff()
        data = self.scenario().data
        self.assertTrue(data['available'])
        self.assertAlmostEqual(data['baseline']['net_cost_eur'], 2.59, places=2)
        self.assertEqual(data['difference_net_cost_eur'], 0.0)

    def test_scenario_consumption_reduction_lowers_cost(self):
        self.activate_tariff()
        data = self.scenario(consumption_change_pct=-50).data
        self.assertAlmostEqual(data['scenario']['import_kwh'], 1.44, places=6)
        self.assertAlmostEqual(data['difference_net_cost_eur'], -2.16, places=2)

    def test_scenario_alternative_tariff_is_not_stored(self):
        self.activate_tariff()
        data = self.scenario(tariff={'rate_standard_eur_per_kwh': 0.5, 'rate_peak_eur_per_kwh': 0.5}).data
        self.assertAlmostEqual(data['scenario']['net_cost_eur'], 4.32, places=2)
        self.assertAlmostEqual(data['difference_net_cost_eur'], 1.73, places=2)
        self.assertEqual(TariffPlan.objects.count(), 1)

    def test_scenario_validation(self):
        self.activate_tariff()
        self.assertEqual(self.scenario(consumption_change_pct=-150).status_code, 400)
        self.assertEqual(self.scenario(tariff={'rate_standard_eur_per_kwh': -1,
                                               'rate_peak_eur_per_kwh': 1}).status_code, 400)
