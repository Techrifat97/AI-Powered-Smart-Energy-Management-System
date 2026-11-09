from datetime import datetime, timedelta, timezone

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from monitoring.models import Building, EnergyReading, Meter
from monitoring.services.aggregation import summarize_building


class BuildingAggregationTests(TestCase):
    def setUp(self):
        self.building = Building.objects.create(name='Energy lab', baseline_kwh_per_day=250)
        self.timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.meters = {
            category: Meter.objects.create(
                building=self.building, device_id=f'TEST-{category}', meter_type=category,
            )
            for category, _ in Meter.METER_TYPES
        }

    def add_reading(self, category, energy, power=0.0, timestamp=None, meter=None, duration=60):
        reading = EnergyReading(
            meter=meter if meter is not None else self.meters[category],
            timestamp=timestamp if timestamp is not None else self.timestamp,
            energy_kwh=energy, power_kw=power, interval_seconds=duration,
        )
        reading.full_clean()
        reading.save()
        return reading

    def assert_main_unavailable(self, summary, *, ambiguous=False):
        for field in [
            'total_consumption_kwh', 'average_daily_kwh',
            'peak_demand_kw', 'net_grid_consumption_kwh',
        ]:
            with self.subTest(field=field):
                self.assertIsNone(summary[field])
        self.assertFalse(summary['main_data_available'])
        self.assertEqual(summary['main_data_ambiguous'], ambiguous)

    def test_main_and_submeters_are_not_double_counted(self):
        self.add_reading('ELECTRICITY', 100, 20)
        self.add_reading('HVAC', 40, 90)
        self.add_reading('LIGHTING', 20, 80)
        self.add_reading('SOLAR', 30, 500)

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 100)
        self.assertEqual(summary['total_solar_generated_kwh'], 30)
        self.assertEqual(summary['net_grid_consumption_kwh'], 70)
        self.assertEqual(summary['peak_demand_kw'], 20)
        self.assertEqual(summary['average_daily_kwh'], 100)
        self.assertEqual(summary['baseline_kwh_per_day'], 250)
        self.assertEqual(summary['total_readings_count'], 4)
        self.assertEqual(summary['main_meter_count'], 1)
        self.assertEqual(summary['main_readings_count'], 1)
        self.assertEqual(summary['solar_readings_count'], 1)
        self.assertTrue(summary['main_data_available'])
        self.assertFalse(summary['main_data_ambiguous'])

    def test_recorded_zero_is_available_and_not_replaced_by_baseline(self):
        self.add_reading('ELECTRICITY', 0, 0)
        self.add_reading('SOLAR', 0, 0)

        summary = summarize_building(self.building)

        for field in ['total_consumption_kwh', 'average_daily_kwh', 'peak_demand_kw', 'net_grid_consumption_kwh']:
            self.assertEqual(summary[field], 0)
        self.assertTrue(summary['main_data_available'])
        self.assertEqual(summary['main_readings_count'], 1)
        self.assertEqual(summary['recorded_main_days_count'], 1)
        self.assertEqual(summary['baseline_kwh_per_day'], 250)

    def test_missing_main_readings_are_not_measured_zero(self):
        summary = summarize_building(self.building)

        self.assert_main_unavailable(summary)
        self.assertEqual(summary['main_meter_count'], 0)
        self.assertEqual(summary['main_readings_count'], 0)
        self.assertEqual(summary['recorded_main_days_count'], 0)
        self.assertEqual(summary['total_readings_count'], 0)
        self.assertIsNone(summary['total_solar_generated_kwh'])
        self.assertEqual(summary['solar_readings_count'], 0)
        self.assertIsNone(summary['earliest_reading'])
        self.assertIsNone(summary['latest_reading'])

    def test_submeter_only_data_does_not_infer_building_consumption(self):
        self.add_reading('HVAC', 40, 90)
        self.add_reading('LIGHTING', 20, 80)

        summary = summarize_building(self.building)

        self.assert_main_unavailable(summary)
        self.assertEqual(summary['total_readings_count'], 2)
        self.assertEqual(summary['main_readings_count'], 0)

    def test_solar_only_data_keeps_solar_totals_and_timestamps(self):
        self.add_reading('SOLAR', 30, 500)

        summary = summarize_building(self.building)

        self.assert_main_unavailable(summary)
        self.assertEqual(summary['total_solar_generated_kwh'], 30)
        self.assertEqual(summary['solar_readings_count'], 1)
        self.assertEqual(summary['total_readings_count'], 1)
        self.assertEqual(summary['earliest_reading'], self.timestamp)
        self.assertEqual(summary['latest_reading'], self.timestamp)

    def test_deactivation_does_not_remove_historical_energy(self):
        self.add_reading('ELECTRICITY', 100, 20)
        self.add_reading('SOLAR', 30, 50)
        self.building.meters.update(is_active=False)

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 100)
        self.assertEqual(summary['total_solar_generated_kwh'], 30)
        self.assertEqual(summary['net_grid_consumption_kwh'], 70)
        self.assertEqual(summary['active_meters_count'], 0)
        self.assertTrue(summary['main_data_available'])

    def test_other_buildings_cannot_affect_totals_or_main_ambiguity(self):
        self.add_reading('ELECTRICITY', 10, 2)
        self.add_reading('SOLAR', 2, 5)
        other = Building.objects.create(name='Other building')
        other_main = Meter.objects.create(building=other, device_id='OTHER-MAIN')
        other_solar = Meter.objects.create(building=other, device_id='OTHER-SOLAR', meter_type='SOLAR')
        self.add_reading('ELECTRICITY', 999, 999, meter=other_main)
        self.add_reading('SOLAR', 777, 777, meter=other_solar)

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 10)
        self.assertEqual(summary['total_solar_generated_kwh'], 2)
        self.assertEqual(summary['peak_demand_kw'], 2)
        self.assertEqual(summary['total_readings_count'], 2)
        self.assertEqual(summary['main_meter_count'], 1)
        self.assertEqual(summarize_building(other)['total_consumption_kwh'], 999)

    def test_unknown_coverage_of_multiple_recording_mains_is_ambiguous(self):
        self.add_reading('ELECTRICITY', 100, 20)
        other_main = Meter.objects.create(building=self.building, device_id='SECOND-MAIN')
        self.add_reading('ELECTRICITY', 25, 10, self.timestamp + timedelta(days=1), other_main, duration=None)
        self.add_reading('SOLAR', 30, 50)

        summary = summarize_building(self.building)

        self.assert_main_unavailable(summary, ambiguous=True)
        self.assertEqual(summary['main_meter_count'], 2)
        self.assertEqual(summary['main_readings_count'], 2)
        self.assertEqual(summary['total_solar_generated_kwh'], 30)
        response = APIClient().get(reverse('building-summary', args=[self.building.pk]))
        self.assertEqual(response.status_code, 200)
        self.assert_main_unavailable(response.data, ambiguous=True)

    def test_main_without_readings_does_not_make_recorded_main_ambiguous(self):
        self.add_reading('ELECTRICITY', 100, 20)
        Meter.objects.create(building=self.building, device_id='UNUSED-MAIN')

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 100)
        self.assertEqual(summary['main_meter_count'], 1)
        self.assertTrue(summary['main_data_available'])
        self.assertFalse(summary['main_data_ambiguous'])

    def test_solar_excess_is_a_signed_recorded_balance(self):
        self.add_reading('ELECTRICITY', 10, 2)
        self.add_reading('SOLAR', 30, 5)

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 10)
        self.assertEqual(summary['total_solar_generated_kwh'], 30)
        self.assertEqual(summary['net_grid_consumption_kwh'], -20)

    def test_daily_average_uses_recorded_dates_without_filling_gaps(self):
        self.add_reading('ELECTRICITY', 10, timestamp=self.timestamp.replace(hour=1))
        self.add_reading('ELECTRICITY', 30, timestamp=self.timestamp.replace(hour=23))
        self.add_reading('ELECTRICITY', 20, timestamp=self.timestamp + timedelta(days=3))

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 60)
        self.assertEqual(summary['recorded_main_days_count'], 2)
        self.assertEqual(summary['average_daily_kwh'], 30)

    @override_settings(TIME_ZONE='Europe/Berlin')
    def test_daily_average_groups_by_utc_date(self):
        self.add_reading('ELECTRICITY', 10, timestamp=self.timestamp.replace(hour=23, minute=30))
        self.add_reading('ELECTRICITY', 30, timestamp=(self.timestamp + timedelta(days=1)).replace(hour=0, minute=30))

        summary = summarize_building(self.building)

        self.assertEqual(summary['recorded_main_days_count'], 2)
        self.assertEqual(summary['average_daily_kwh'], 20)

    def test_time_window_includes_start_excludes_end_and_filters_solar(self):
        end = self.timestamp + timedelta(hours=1)
        self.add_reading('ELECTRICITY', 1000, 1000, self.timestamp - timedelta(minutes=1))
        self.add_reading('ELECTRICITY', 10, 2, self.timestamp)
        self.add_reading('ELECTRICITY', 11, 3, self.timestamp + timedelta(minutes=30))
        self.add_reading('ELECTRICITY', 900, 900, end)
        self.add_reading('SOLAR', 5, 50, self.timestamp + timedelta(minutes=15))
        self.add_reading('SOLAR', 500, 500, end)

        summary = summarize_building(self.building, start=self.timestamp, end=end)

        self.assertEqual(summary['total_consumption_kwh'], 21)
        self.assertEqual(summary['total_solar_generated_kwh'], 5)
        self.assertEqual(summary['net_grid_consumption_kwh'], 16)
        self.assertEqual(summary['peak_demand_kw'], 3)
        self.assertEqual(summary['total_readings_count'], 3)
        self.assertEqual(summary['earliest_reading'], self.timestamp)
        self.assertEqual(summary['latest_reading'], self.timestamp + timedelta(minutes=30))
        self.assertEqual(summarize_building(self.building)['total_consumption_kwh'], 1921)
        self.assertEqual(summarize_building(self.building, end=self.timestamp)['total_consumption_kwh'], 1000)
        self.assertEqual(summarize_building(self.building, start=end)['total_consumption_kwh'], 900)

    def test_time_window_can_remove_main_ambiguity_without_selecting_a_meter(self):
        self.add_reading('ELECTRICITY', 100, 20)
        other_main = Meter.objects.create(building=self.building, device_id='LATER-MAIN')
        self.add_reading('ELECTRICITY', 25, 10, self.timestamp + timedelta(days=1), other_main)

        summary = summarize_building(self.building, end=self.timestamp + timedelta(hours=1))

        self.assertEqual(summary['total_consumption_kwh'], 100)
        self.assertEqual(summary['main_meter_count'], 1)
        self.assertTrue(summary['main_data_available'])
        self.assertFalse(summarize_building(self.building)['main_data_ambiguous'])
        self.assertEqual(summarize_building(self.building)['total_consumption_kwh'], 125)

    def test_invalid_windows_are_rejected(self):
        for window in [
            {'start': self.timestamp.replace(tzinfo=None)},
            {'end': '2026-01-01'},
            {'start': self.timestamp, 'end': self.timestamp},
            {'start': self.timestamp + timedelta(days=1), 'end': self.timestamp},
        ]:
            with self.subTest(window=window):
                with self.assertRaises(ValueError):
                    summarize_building(self.building, **window)
        with self.assertRaises(ValueError):
            summarize_building(Building(name='Unsaved'))

    def test_small_interval_energy_is_not_rounded_to_zero(self):
        self.add_reading('ELECTRICITY', 0.001, 0.06)
        self.add_reading('SOLAR', 0.0002, 0.012)

        summary = summarize_building(self.building)

        self.assertEqual(summary['total_consumption_kwh'], 0.001)
        self.assertEqual(summary['total_solar_generated_kwh'], 0.0002)
        self.assertAlmostEqual(summary['net_grid_consumption_kwh'], 0.0008)

    def test_endpoint_preserves_existing_keys_and_adds_availability(self):
        self.add_reading('ELECTRICITY', 100, 20)
        self.add_reading('HVAC', 40, 90)
        self.add_reading('LIGHTING', 20, 80)
        self.add_reading('SOLAR', 30, 500)

        response = APIClient().get(reverse('building-summary', args=[self.building.pk]))

        self.assertEqual(response.status_code, 200)
        existing_keys = {
            'building_id', 'building_name', 'location', 'area_sqm', 'baseline_kwh_per_day',
            'total_consumption_kwh', 'average_daily_kwh', 'peak_demand_kw',
            'total_solar_generated_kwh', 'net_grid_consumption_kwh', 'active_meters_count',
            'total_readings_count', 'earliest_reading', 'latest_reading',
        }
        self.assertTrue(existing_keys.issubset(response.data))
        self.assertEqual(response.data['total_consumption_kwh'], 100)
        self.assertEqual(response.data['total_solar_generated_kwh'], 30)
        self.assertEqual(response.data['peak_demand_kw'], 20)
        self.assertEqual(response.data['active_meters_count'], 4)
        self.assertTrue(response.data['main_data_available'])
        self.assertEqual(response.data['main_readings_count'], 1)

    def test_endpoint_distinguishes_missing_from_zero_and_keeps_404(self):
        client = APIClient()
        url = reverse('building-summary', args=[self.building.pk])
        missing = client.get(url)
        self.assertEqual(missing.status_code, 200)
        self.assert_main_unavailable(missing.data)

        self.add_reading('ELECTRICITY', 0, 0)
        measured = client.get(url)
        self.assertEqual(measured.data['total_consumption_kwh'], 0)
        self.assertEqual(measured.data['average_daily_kwh'], 0)
        self.assertTrue(measured.data['main_data_available'])
        self.assertEqual(client.get(reverse('building-summary', args=[self.building.pk + 100])).status_code, 404)
