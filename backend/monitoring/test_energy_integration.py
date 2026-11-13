"""Manually checkable shared measurement contracts across S1, S2 and S3."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as django_timezone
from rest_framework.test import APIClient

from analysis.models import TariffPlan
from analysis.services.costs import cost_analysis
from coach.models import AIRecommendation, ConsumptionForecast, LLMRequestLog
from coach.services.forecaster import ConsumptionForecaster
from coach.services.scorer import SustainabilityScorer
from monitoring.models import Building, Meter, EnergyReading
from monitoring.services.aggregation import building_energy_report, summarize_building


@patch.dict('os.environ', {'OPENAI_API_KEY': ''})
class EnergyIntegrationTests(TestCase):
    def setUp(self):
        self.building = Building.objects.create(name='Integration lab', baseline_kwh_per_day=250)
        self.main = Meter.objects.create(building=self.building, device_id='MAIN')
        self.solar = Meter.objects.create(building=self.building, device_id='PV', meter_type='SOLAR')
        self.start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.client = APIClient()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username='integration_user', password='password123')
        self.client.force_authenticate(user=self.user)

    def reading(self, meter, energy, start=None, duration=3600, power=3):
        return EnergyReading.objects.create(meter=meter, timestamp=start or self.start,
            energy_kwh=energy, power_kw=power, interval_seconds=duration)

    def no_solar(self):
        self.building.has_solar_installation = False
        self.building.save(update_fields=['has_solar_installation'])

    def tariff(self, **changes):
        values = dict(name='Explicit MVP tariff', rate_standard_eur_per_kwh=.30,
            rate_peak_eur_per_kwh=.50, solar_feed_in_eur_per_kwh=.08,
            peak_start_hour=11, peak_end_hour=16)
        values.update(changes)
        return TariffPlan.objects.create(**values)

    def costs(self):
        return self.client.get(reverse('building-cost-analysis', args=[self.building.pk])).data

    def recommendations(self):
        return self.client.post(reverse('recommendations-generate'), {'building_id': self.building.pk}, format='json')

    def complete_history(self, energy=5):
        start = (django_timezone.now().astimezone(timezone.utc)
                 .replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2))
        for hour in range(48):
            self.reading(self.main, energy, start + timedelta(hours=hour))
        return start

    def test_zero_energy_does_not_imply_zero_power_or_balance(self):
        self.reading(self.main, 0, power=7)
        self.reading(self.solar, 10, power=20)
        s = summarize_building(self.building)
        self.assertEqual(s['total_consumption_kwh'], 0)
        self.assertEqual(s['peak_demand_kw'], 7)
        self.assertEqual(s['net_grid_consumption_kwh'], -10)
        self.assertEqual(s['estimated_grid_import_kwh'], 0)
        self.assertEqual(s['estimated_grid_export_kwh'], 10)

    def test_known_nonoverlapping_replacement_is_allowed_and_inactive_history_retained(self):
        self.no_solar()
        old = self.reading(self.main, 4)
        self.main.is_active = False
        self.main.save()
        replacement = Meter.objects.create(building=self.building, device_id='REPLACEMENT')
        self.reading(replacement, 6, self.start + timedelta(hours=1), duration=60)
        s = summarize_building(self.building)
        self.assertEqual(s['total_consumption_kwh'], 10)
        self.assertEqual(s['main_meter_count'], 2)
        self.assertFalse(s['main_data_ambiguous'])
        self.assertTrue(s['main_coverage_complete'])
        self.assertTrue(EnergyReading.objects.filter(pk=old.pk).exists())

    def test_hourly_minute_overlap_across_mains_is_unavailable(self):
        self.reading(self.main, 10)
        replacement = Meter.objects.create(building=self.building, device_id='OVERLAP')
        self.reading(replacement, 1, self.start + timedelta(minutes=30), duration=60)
        s = summarize_building(self.building)
        self.assertTrue(s['main_data_ambiguous'])
        self.assertEqual(s['main_data_reason'], 'overlapping_intervals')
        self.assertIsNone(s['total_consumption_kwh'])
        self.assertIsNone(s['peak_demand_kw'])
        self.assertIsNone(self.costs()['estimated_import_cost_eur'])
        self.assertEqual(self.recommendations().data['availability']['reason'], 'overlapping_intervals')

    def test_overlap_on_same_meter_is_also_rejected(self):
        self.reading(self.main, 10)
        self.reading(self.main, 1, self.start + timedelta(minutes=1), duration=60)
        self.assertTrue(summarize_building(self.building)['main_data_ambiguous'])

    def test_window_does_not_hide_overlapping_hourly_reading_starting_before_it(self):
        self.reading(self.main, 10)
        self.reading(self.main, 1, self.start + timedelta(minutes=30), duration=60)
        s = summarize_building(self.building, start=self.start + timedelta(minutes=30))
        self.assertTrue(s['main_data_ambiguous'])

    def test_window_end_does_not_prorate_energy(self):
        self.reading(self.main, 10)
        s = summarize_building(self.building, end=self.start + timedelta(minutes=30))
        self.assertIsNone(s['total_consumption_kwh'])
        self.assertEqual(s['main_data_reason'], 'interval_crosses_window_end')

    def test_unknown_duration_preserves_record_but_blocks_dependent_calculations(self):
        row = self.reading(self.main, 10, duration=None, power=10)
        s = summarize_building(self.building)
        self.assertEqual(s['main_data_reason'], 'unknown_duration')
        self.assertIsNone(s['total_consumption_kwh'])
        self.assertIsNone(s['estimated_grid_import_kwh'])
        row.refresh_from_db()
        self.assertIsNone(row.interval_seconds)  # Equal kW/kWh is not evidence of an hour.
        self.assertEqual(row.energy_kwh, 10)

    def test_unknown_duration_solar_is_not_treated_as_known_energy_coverage(self):
        self.reading(self.main, 10)
        self.reading(self.solar, 5, duration=None)
        s = summarize_building(self.building)
        self.assertEqual(s['total_consumption_kwh'], 10)
        self.assertIsNone(s['total_solar_generated_kwh'])
        self.assertIsNone(s['net_grid_consumption_kwh'])

    def test_missing_solar_is_not_zero_and_no_installation_is_explicit(self):
        self.reading(self.main, 10)
        s = summarize_building(self.building)
        self.assertIsNone(s['total_solar_generated_kwh'])
        self.assertFalse(s['grid_estimates_available'])
        self.building.has_solar_installation = True
        self.building.save()
        self.assertIsNone(summarize_building(self.building)['estimated_grid_import_kwh'])
        self.no_solar()
        s = summarize_building(self.building)
        self.assertEqual(s['total_solar_generated_kwh'], 0)
        self.assertEqual(s['estimated_grid_import_kwh'], 10)
        self.assertEqual(s['solar_data_reason'], 'confirmed_no_installation')

    def test_recorded_zero_solar_is_valid_evidence_even_if_inventory_unknown(self):
        self.reading(self.main, 10)
        self.reading(self.solar, 0)
        self.assertEqual(summarize_building(self.building)['estimated_grid_import_kwh'], 10)

    def test_installation_false_conflicts_with_historical_solar_not_erases_it(self):
        self.no_solar()
        self.reading(self.main, 10)
        row = self.reading(self.solar, 2)
        s = summarize_building(self.building)
        self.assertEqual(s['solar_data_reason'], 'installation_status_conflicts_with_readings')
        self.assertIsNone(s['estimated_grid_import_kwh'])
        self.assertTrue(EnergyReading.objects.filter(pk=row.pk).exists())

    def test_mismatching_or_overlapping_solar_does_not_produce_grid_estimates(self):
        self.reading(self.main, 10)
        self.reading(self.solar, 2, duration=60)
        s = summarize_building(self.building)
        self.assertEqual(s['net_grid_consumption_kwh'], 8)  # Signed recorded balance only.
        self.assertIsNone(s['estimated_grid_import_kwh'])
        extra = Meter.objects.create(building=self.building, device_id='PV2', meter_type='SOLAR')
        self.reading(extra, 3)
        self.assertEqual(summarize_building(self.building)['solar_data_reason'], 'overlapping_intervals')

    def test_export_day_import_night_do_not_cancel_for_pricing(self):
        self.reading(self.main, 0)
        self.reading(self.solar, 10)
        night = self.start + timedelta(hours=12)
        self.reading(self.main, 10, night)
        self.reading(self.solar, 0, night)
        self.tariff()
        s = summarize_building(self.building)
        costs = self.costs()
        self.assertEqual(s['net_grid_consumption_kwh'], 0)
        self.assertEqual(s['estimated_grid_import_kwh'], 10)
        self.assertEqual(s['estimated_grid_export_kwh'], 10)
        self.assertEqual(costs['estimated_import_cost_eur'], 3)
        self.assertEqual(costs['estimated_export_credit_eur'], .8)
        self.assertEqual(costs['estimated_net_cost_eur'], 2.2)
        self.assertFalse(costs['coverage_complete'])
        self.assertFalse(costs['complete_bill_available'])
        self.assertIsNone(costs['net_cost_eur'])  # Gaps cannot become a complete bill.

    def test_peak_standard_and_feed_in_fields_are_used_explicitly(self):
        self.reading(self.main, 10)
        self.reading(self.solar, 2)
        later = self.start + timedelta(hours=1)
        self.reading(self.main, 0, later)
        self.reading(self.solar, 5, later)
        self.tariff()
        c = self.costs()
        self.assertEqual(c['estimated_import_cost_eur'], 4)
        self.assertEqual(c['estimated_export_credit_eur'], .4)
        self.assertEqual(c['gross_cost_eur'], 5)
        self.assertEqual(c['solar_savings_eur'], 1)  # Only self-consumed 2, not all solar 7.
        self.assertEqual(c['net_cost_eur'], 3.6)

    def test_tariff_missing_ambiguous_invalid_are_not_defaults(self):
        self.no_solar()
        self.reading(self.main, 10)
        self.assertEqual(self.costs()['cost_estimates_reason'], 'missing_active_tariff')
        tariff = self.tariff()
        self.tariff(name='Conflicting tariff')
        self.assertEqual(self.costs()['cost_estimates_reason'], 'ambiguous_active_tariffs')
        TariffPlan.objects.exclude(pk=tariff.pk).delete()
        tariff.rate_standard_eur_per_kwh = -1
        tariff.save()
        self.assertEqual(self.costs()['cost_estimates_reason'], 'invalid_tariff')
        self.assertIsNone(self.costs()['net_cost_eur'])

    def test_interval_crossing_price_boundary_needs_finer_data(self):
        self.no_solar()
        self.reading(self.main, 10, self.start.replace(hour=10, minute=30))
        tariff = self.tariff()
        self.assertEqual(self.costs()['cost_estimates_reason'], 'interval_crosses_tariff_band')
        tariff.rate_peak_eur_per_kwh = tariff.rate_standard_eur_per_kwh
        tariff.save()
        self.assertEqual(self.costs()['estimated_import_cost_eur'], 3)

    def test_overnight_peak_band_and_exact_end_boundary(self):
        self.no_solar()
        self.reading(self.main, 10, self.start.replace(hour=23))
        self.reading(self.main, 10, self.start.replace(hour=6))
        self.tariff(peak_start_hour=22, peak_end_hour=6)
        self.assertEqual(self.costs()['estimated_import_cost_eur'], 8)

    def test_two_complete_days_forecast_uses_main_only_and_all_subsystems_agree(self):
        self.no_solar()
        start = self.complete_history()
        hvac = Meter.objects.create(building=self.building, device_id='HVAC', meter_type='HVAC')
        lighting = Meter.objects.create(building=self.building, device_id='LIGHT', meter_type='LIGHTING')
        self.reading(hvac, 40, start, power=999)
        self.reading(lighting, 20, start, power=999)
        other = Building.objects.create(name='Other', has_solar_installation=False)
        other_main = Meter.objects.create(building=other, device_id='OTHER')
        self.reading(other_main, 999, start)
        self.tariff(rate_peak_eur_per_kwh=.30)
        s1 = self.client.get(reverse('building-summary', args=[self.building.pk])).data
        s2 = self.recommendations()
        s3 = self.costs()
        self.assertEqual(s2.status_code, 201)
        for s in [s1, s2.data['energy_summary'], s3['energy_summary']]:
            self.assertEqual(s['total_consumption_kwh'], 240)
            self.assertEqual(s['peak_demand_kw'], 3)
            self.assertEqual(s['full_day_average_kwh'], 120)
        self.assertEqual(s2.data['forecast_availability']['observed_full_day_average_kwh'], 120)
        self.assertEqual(s3['estimated_import_cost_eur'], 72)
        self.assertTrue(AIRecommendation.objects.filter(building=self.building).exists())
        self.assertTrue(all(r.estimated_savings_eur is None for r in AIRecommendation.objects.all()))
        self.assertIsNone(s2.data['sustainability_assessment']['estimated_daily_cost_eur'])

    def test_s2_missing_ambiguous_unknown_and_partial_data_do_not_fall_back(self):
        for duration in [None, 60]:
            EnergyReading.objects.all().delete()
            if duration is not None:
                self.reading(self.main, 0, duration=duration)
            response = self.recommendations()
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.data['availability']['available'])
            self.assertEqual(response.data['recommendations'], [])
            self.assertEqual(response.data['engine_telemetry']['status'], 'NOT_RUN')
            forecast = self.client.get(reverse('building-forecast', args=[self.building.pk])).data
            self.assertEqual(forecast['forecast'], [])
            self.assertIsNone(forecast['total_predicted_7d_kwh'])
        self.assertFalse(LLMRequestLog.objects.exists())
        self.assertFalse(ConsumptionForecast.objects.exists())

    def test_s2_complete_zero_days_remain_zero_and_peak_is_independent(self):
        self.no_solar()
        self.complete_history(energy=0)
        response = self.recommendations()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['energy_summary']['peak_demand_kw'], 3)
        self.assertEqual(response.data['forecast_preview']['projected_weekly_total_kwh'], 0)
        self.assertTrue(all(r.estimated_savings_kwh == 0 for r in AIRecommendation.objects.all()))

    def test_s2_missing_solar_prevents_carbon_and_recommendation_claims(self):
        self.complete_history()
        response = self.recommendations()
        self.assertFalse(response.data['availability']['available'])
        self.assertIsNone(response.data['sustainability_assessment']['daily_carbon_kg_co2'])
        self.assertIsNone(response.data['sustainability_assessment']['sustainability_score'])
        self.assertFalse(LLMRequestLog.objects.exists())

    def test_partial_days_and_gaps_do_not_become_full_day_forecasting_history(self):
        self.no_solar()
        self.reading(self.main, 100)
        self.reading(self.main, 20, self.start + timedelta(days=3))
        report = building_energy_report(self.building)
        self.assertEqual(report['summary']['average_daily_kwh'], 60)
        self.assertEqual(report['complete_days'], [])
        self.assertIsNone(report['summary']['full_day_average_kwh'])
        self.assertFalse(report['summary']['main_coverage_complete'])

    def test_cross_midnight_interval_not_arbitrarily_split_into_daily_totals(self):
        self.no_solar()
        self.reading(self.main, 100, self.start.replace(hour=23), duration=7200)
        self.assertEqual(building_energy_report(self.building)['complete_days'], [])

    def test_scorer_uses_supplied_import_estimate_and_never_daily_netting(self):
        result = SustainabilityScorer.evaluate(10, 20, 10, import_daily_kwh=10)
        self.assertEqual(result['daily_carbon_kg_co2'], 3.85)
        self.assertIsNone(result['estimated_daily_cost_eur'])
        self.assertFalse(SustainabilityScorer.evaluate(0, 0, 0)['available'])

    def test_duration_validation_and_database_constraint(self):
        for duration in [None, 60, 3600]:
            r = EnergyReading(meter=self.main, timestamp=self.start, energy_kwh=0, interval_seconds=duration)
            r.full_clean()
        for duration in [0, -1]:
            with self.subTest(duration=duration):
                r = EnergyReading(meter=self.main, timestamp=self.start, energy_kwh=0, interval_seconds=duration)
                with self.assertRaises(ValidationError):
                    r.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.reading(self.main, 0, duration=duration)

    def test_unknown_earlier_duration_cannot_prove_forecast_window_coverage(self):
        self.no_solar()
        self.complete_history()
        self.reading(self.main, 1, self.start, duration=None)
        forecaster = ConsumptionForecaster()
        self.assertEqual(forecaster.generate_forecast(self.building), [])
        self.assertEqual(forecaster.availability['reason'], 'unknown_duration_before_window')

    def test_live_provider_payload_is_serializable_but_external_call_is_mocked(self):
        from coach.services.llm_coach import SustainabilityCoachService
        self.no_solar()
        self.reading(self.main, 10)
        response = Mock()
        response.choices = [Mock(message=Mock(content='[{"title":"Scenario", "estimated_savings_kwh":1, "estimated_savings_eur":999}]'))]
        response.usage = None
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-unit-test-no-network'}), patch('openai.OpenAI') as client:
            client.return_value.chat.completions.create.return_value = response
            result = SustainabilityCoachService.generate_recommendations(
                self.building, summarize_building(self.building), [], 15)
            client.return_value.chat.completions.create.assert_called_once()
        self.assertEqual(result['source'], 'OPENAI')
        self.assertIsNone(result['recommendations'][0].estimated_savings_eur)

    def test_s3_zero_import_and_export_are_valid_zero_costs(self):
        self.no_solar()
        self.reading(self.main, 0, power=7)
        self.tariff()
        costs = self.costs()
        self.assertTrue(costs['cost_estimates_available'])
        self.assertEqual(costs['net_cost_eur'], 0)
        self.assertEqual(costs['estimated_import_cost_eur'], 0)
        self.assertEqual(costs['estimated_export_credit_eur'], 0)
        self.assertEqual(costs['energy_summary']['peak_demand_kw'], 7)

    def test_s2_unknown_main_duration_does_not_generate_a_baseline_forecast(self):
        self.no_solar()
        self.reading(self.main, 100, duration=None)
        response = self.recommendations()
        self.assertEqual(response.data['availability']['reason'], 'unknown_duration')
        self.assertIsNone(response.data['energy_summary']['total_consumption_kwh'])
        self.assertIsNone(response.data['forecast_preview']['projected_weekly_total_kwh'])
        self.assertFalse(LLMRequestLog.objects.exists())

    def test_unknown_earlier_solar_cannot_be_overridden_by_no_installation_flag(self):
        self.no_solar()
        self.reading(self.solar, 10, duration=None)
        later = self.start + timedelta(hours=1)
        self.reading(self.main, 10, later)
        summary = summarize_building(self.building, start=later)
        self.assertIsNone(summary['estimated_grid_import_kwh'])
        self.assertEqual(summary['solar_data_reason'], 'installation_status_conflicts_with_readings')
