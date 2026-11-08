from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
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


class MonitoringModelTests(TestCase):
    def setUp(self):
        self.building = Building.objects.create(name="Model Test Building")
        self.meter = Meter.objects.create(building=self.building, device_id="MODEL-001")
        self.timestamp = datetime(2026, 11, 1, 12, tzinfo=datetime_timezone.utc)

    def make_reading(self, **changes):
        values = {
            'meter': self.meter, 'timestamp': self.timestamp,
            'energy_kwh': 0.1, 'power_kw': 2.0, 'voltage': 230.0,
        }
        values.update(changes)
        return EnergyReading(**values)

    def test_valid_measurements_and_zero_values_for_all_meter_types(self):
        Building(name="Zero baseline", area_sqm=0.01, baseline_kwh_per_day=0).full_clean()
        for index, (meter_type, _) in enumerate(Meter.METER_TYPES):
            with self.subTest(meter_type=meter_type):
                meter = Meter(building=self.building, device_id=f"VALID-{index}", meter_type=meter_type)
                meter.full_clean()
                meter.save()
                for minute, value in enumerate([0.0, 0.1]):
                    reading = self.make_reading(
                        meter=meter, timestamp=self.timestamp + timedelta(minutes=minute),
                        energy_kwh=value, power_kw=2.0 if value else 0.0,
                        voltage=230.0 if value else 0.0,
                    )
                    reading.full_clean()
                    reading.save()
                    reading.refresh_from_db()
                    self.assertEqual(reading.energy_kwh, value)
                    self.assertIsInstance(reading.energy_kwh, float)
                    self.assertEqual(reading.meter.building_id, self.building.pk)

    def test_building_rejects_invalid_area_and_baseline(self):
        for field in ['area_sqm', 'baseline_kwh_per_day']:
            invalid_values = [-1, float('nan'), float('inf'), -float('inf'), None, 'invalid']
            if field == 'area_sqm':
                invalid_values.append(0)
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    building = Building(name="Invalid building", **{field: value})
                    with self.assertRaises(ValidationError) as error:
                        building.full_clean()
                    self.assertIn(field, error.exception.message_dict)

    def test_reading_rejects_invalid_measurements(self):
        for field in ['energy_kwh', 'power_kw', 'voltage']:
            for value in [-1, float('nan'), float('inf'), -float('inf'), None, 'invalid']:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError) as error:
                        self.make_reading(**{field: value}).full_clean()
                    self.assertIn(field, error.exception.message_dict)

    def test_timestamp_requires_aware_utc_minute_boundary(self):
        cases = [
            self.timestamp.replace(tzinfo=None),
            self.timestamp.astimezone(datetime_timezone(timedelta(hours=2))),
            self.timestamp + timedelta(seconds=1),
            self.timestamp + timedelta(microseconds=1),
            'not a timestamp', None,
        ]
        for timestamp in cases:
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValidationError) as error:
                    self.make_reading(timestamp=timestamp).full_clean()
                self.assertIn('timestamp', error.exception.message_dict)

    def test_meter_rejects_unsupported_type_unit_and_duplicate_device_id(self):
        for field, value in [('meter_type', 'BATTERY'), ('meter_type', 'PLUG'), ('unit', 'Wh')]:
            with self.subTest(field=field, value=value):
                meter = Meter(building=self.building, device_id="NEW-METER", **{field: value})
                with self.assertRaises(ValidationError) as error:
                    meter.full_clean()
                self.assertIn(field, error.exception.message_dict)
        with self.assertRaises(ValidationError) as error:
            Meter(building=self.building, device_id=self.meter.device_id).full_clean()
        self.assertIn('device_id', error.exception.message_dict)

    def test_database_rejects_invalid_building_values_without_full_clean(self):
        for field in ['area_sqm', 'baseline_kwh_per_day']:
            values = [-1, float('nan'), float('inf'), -float('inf')]
            if field == 'area_sqm':
                values.append(0)
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        Building.objects.create(name="Invalid database row", **{field: value})

    def test_database_rejects_invalid_readings_without_full_clean(self):
        for field in ['energy_kwh', 'power_kw', 'voltage']:
            for value in [-1, float('nan'), float('inf'), -float('inf')]:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(IntegrityError), transaction.atomic():
                        self.make_reading(**{field: value}).save()

    def test_database_rejects_unsupported_meter_type_and_unit(self):
        for field, value in [('meter_type', 'UNKNOWN'), ('unit', 'Wh')]:
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Meter.objects.create(building=self.building, device_id="BAD-METER", **{field: value})

    def test_duplicate_meter_timestamp_rejected_by_validation_and_database(self):
        self.make_reading().save()
        with self.assertRaises(ValidationError):
            self.make_reading().full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_reading().save()
        # Bulk insertion cannot bypass the database uniqueness constraint either.
        next_minute = self.timestamp + timedelta(minutes=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EnergyReading.objects.bulk_create([
                self.make_reading(timestamp=next_minute), self.make_reading(timestamp=next_minute)
            ])
        self.assertEqual(self.meter.readings.count(), 1)

    def test_different_meters_and_different_intervals_are_allowed(self):
        other = Meter.objects.create(building=self.building, device_id="MODEL-002", meter_type='SOLAR')
        for values in [
            {}, {'meter': other}, {'timestamp': self.timestamp + timedelta(minutes=1)}
        ]:
            reading = self.make_reading(**values)
            reading.full_clean()
            reading.save()
        self.assertEqual(EnergyReading.objects.count(), 3)

    def test_deactivation_preserves_historical_readings(self):
        reading = self.make_reading()
        reading.full_clean()
        reading.save()
        self.meter.is_active = False
        self.meter.save(update_fields=['is_active'])
        reading.refresh_from_db()
        reading.full_clean()
        self.assertFalse(reading.meter.is_active)
        self.assertEqual(self.meter.readings.count(), 1)
        self.assertEqual(reading.energy_kwh, 0.1)


class MonitoringMigrationTests(TransactionTestCase):
    """Exercise the new migration on disposable legacy tables, never user data."""

    migrate_from = ('monitoring', '0001_initial')
    migrate_to = ('monitoring', '0002_strengthen_s1_models')

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps
        self.addCleanup(self.restore_latest_schema)
        self.old_reading = self.old_apps.get_model('monitoring', 'EnergyReading')
        building = self.old_apps.get_model('monitoring', 'Building').objects.create(name="Legacy demo")
        self.old_meter = self.old_apps.get_model('monitoring', 'Meter').objects.create(
            building=building, device_id="LEGACY-001", is_active=False
        )
        self.timestamp = datetime(2026, 11, 1, 12, tzinfo=datetime_timezone.utc)

    def restore_latest_schema(self):
        # Remove only this test's disposable legacy rows so a deliberately failed
        # migration cannot leave the test database on the old schema.
        self.old_reading.objects.all().delete()
        self.old_apps.get_model('monitoring', 'Meter').objects.all().delete()
        self.old_apps.get_model('monitoring', 'Building').objects.all().delete()
        MigrationExecutor(connection).migrate([self.migrate_to])

    def test_migration_preserves_hourly_demo_energy_and_inactive_history(self):
        reading = self.old_reading.objects.create(
            meter=self.old_meter, timestamp=self.timestamp, energy_kwh=6.0, power_kw=6.0
        )
        MigrationExecutor(connection).migrate([self.migrate_to])
        current = EnergyReading.objects.get(pk=reading.pk)
        self.assertEqual(current.timestamp, self.timestamp)
        self.assertEqual(current.energy_kwh, 6.0)  # Still an hour's energy, not 0.1 kWh.
        self.assertEqual(current.power_kw, 6.0)
        self.assertEqual(current.meter_id, self.old_meter.pk)
        self.assertFalse(current.meter.is_active)

    def test_migration_preserves_all_seeded_demo_readings(self):
        call_command('seed_demo_data', stdout=StringIO())
        self.old_apps.get_model('monitoring', 'Meter').objects.filter(
            device_id='MTR-HVAC-001'
        ).update(is_active=False)
        fields = ['pk', 'meter_id', 'timestamp', 'energy_kwh', 'power_kw', 'voltage']
        before = list(self.old_reading.objects.order_by('pk').values_list(*fields))
        self.assertEqual(len(before), 812)

        MigrationExecutor(connection).migrate([self.migrate_to])

        after = list(EnergyReading.objects.order_by('pk').values_list(*fields))
        self.assertEqual(after, before)
        hvac = Meter.objects.get(device_id='MTR-HVAC-001')
        self.assertFalse(hvac.is_active)
        self.assertEqual(hvac.readings.count(), 14 * 24)

    def test_migration_refuses_duplicates_without_deleting_readings(self):
        for energy in [0.1, 0.2]:
            self.old_reading.objects.create(
                meter=self.old_meter, timestamp=self.timestamp, energy_kwh=energy
            )
        with self.assertRaisesRegex(RuntimeError, r'Duplicate \(meter, timestamp\)'):
            MigrationExecutor(connection).migrate([self.migrate_to])
        self.assertEqual(list(self.old_reading.objects.order_by('pk').values_list('energy_kwh', flat=True)), [0.1, 0.2])

    def test_migration_refuses_invalid_legacy_measurements_without_rewriting(self):
        reading = self.old_reading.objects.create(
            meter=self.old_meter, timestamp=self.timestamp, energy_kwh=-1.0
        )
        with self.assertRaisesRegex(RuntimeError, 'EnergyReading.energy_kwh'):
            MigrationExecutor(connection).migrate([self.migrate_to])
        reading.refresh_from_db()
        self.assertEqual(reading.energy_kwh, -1.0)

    def test_migration_refuses_incompatible_legacy_meter_units(self):
        self.old_meter.unit = 'Wh'
        self.old_meter.save()
        with self.assertRaisesRegex(RuntimeError, 'Meter.unit'):
            MigrationExecutor(connection).migrate([self.migrate_to])
        self.old_meter.refresh_from_db()
        self.assertEqual(self.old_meter.unit, 'Wh')
