from datetime import datetime, timedelta, timezone
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from monitoring.models import Building, EnergyReading
from monitoring.services.aggregation import summarize_building


class IntervalMigrationTests(TransactionTestCase):
    def test_existing_values_and_inactive_history_preserved_without_guessing_duration(self):
        old_target = ('monitoring', '0002_strengthen_s1_models')
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        executor.migrate([old_target])
        apps = executor.loader.project_state([old_target]).apps
        old_building = apps.get_model('monitoring', 'Building').objects.create(name='Legacy hourly-looking data')
        old_meter = apps.get_model('monitoring', 'Meter').objects.create(
            building=old_building, device_id='OLD', is_active=False)
        reading_model = apps.get_model('monitoring', 'EnergyReading')
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for offset in range(2):
            reading_model.objects.create(meter=old_meter, timestamp=start + timedelta(hours=offset),
                                         energy_kwh=6.25, power_kw=6.25, voltage=230)
        fields = ['id', 'meter_id', 'timestamp', 'energy_kwh', 'power_kw', 'voltage']
        before = list(reading_model.objects.order_by('id').values_list(*fields))
        MigrationExecutor(connection).migrate(latest)
        self.assertEqual(list(EnergyReading.objects.order_by('id').values_list(*fields)), before)
        self.assertEqual(list(EnergyReading.objects.values_list('interval_seconds', flat=True)), [None, None])
        building = Building.objects.get(pk=old_building.pk)
        self.assertIsNone(building.has_solar_installation)
        self.assertFalse(building.meters.get().is_active)
        self.assertEqual(summarize_building(building)['main_data_reason'], 'unknown_duration')


class NewDemoMetadataTests(TestCase):
    def test_new_demo_is_explicit_hourly_utc_with_observed_night_solar_zeros(self):
        call_command('seed_demo_data', stdout=StringIO())
        building = Building.objects.get(name='Campus Science Complex - Block A')
        self.assertTrue(building.has_solar_installation)
        self.assertEqual(EnergyReading.objects.count(), 3 * 14 * 24)
        self.assertFalse(EnergyReading.objects.exclude(interval_seconds=3600).exists())
        self.assertTrue(EnergyReading.objects.filter(meter__meter_type='SOLAR', energy_kwh=0).exists())
        summary = summarize_building(building)
        self.assertEqual(summary['complete_main_days_count'], 14)
        self.assertTrue(summary['main_coverage_complete'])
        self.assertTrue(summary['grid_estimates_available'])
        before = list(EnergyReading.objects.order_by('pk').values_list('pk', 'energy_kwh', 'interval_seconds'))
        call_command('seed_demo_data', stdout=StringIO())
        self.assertEqual(list(EnergyReading.objects.order_by('pk').values_list('pk', 'energy_kwh', 'interval_seconds')), before)
