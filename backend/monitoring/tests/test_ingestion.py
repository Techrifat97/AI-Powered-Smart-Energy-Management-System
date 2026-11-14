"""Single-reading contracts and genuine concurrent PostgreSQL ingestion tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase

from monitoring.models import Building, EnergyReading, Meter
from monitoring.services.ingestion import ingest_reading


class IngestionTests(TestCase):
    def setUp(self):
        self.building = Building.objects.create(name='Ingestion laboratory')
        self.meter = Meter.objects.create(building=self.building, device_id='INGEST-MAIN')
        self.timestamp = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        self.values = dict(meter=self.meter, timestamp=self.timestamp, interval_seconds=60,
                           energy_kwh=.1, power_kw=9.0, voltage=230.0)

    def ingest(self, **changes):
        return ingest_reading(**dict(self.values, **changes))

    def legacy(self, *, timestamp=None, duration=3600, meter=None):
        return EnergyReading.objects.create(
            meter=meter or self.meter, timestamp=timestamp or self.timestamp,
            interval_seconds=duration, energy_kwh=6.0, power_kw=6.0, voltage=230,
        )

    def test_valid_reading_stores_values_without_energy_power_equality(self):
        reading, created = self.ingest()
        self.assertTrue(created)
        reading.refresh_from_db()
        self.assertEqual(reading.meter_id, self.meter.pk)
        self.assertEqual(reading.timestamp, self.timestamp)
        self.assertEqual(reading.interval_seconds, 60)
        self.assertEqual(reading.energy_kwh, .1)
        self.assertEqual(reading.power_kw, 9)
        self.assertNotEqual(reading.energy_kwh, reading.power_kw / 60)
        self.assertEqual(reading.voltage, 230)
        self.assertEqual(EnergyReading.objects.count(), 1)
        self.building.refresh_from_db()
        self.assertIsNone(self.building.has_solar_installation)

    def test_integer_meter_identifier_and_zero_measurements_are_valid(self):
        reading, created = self.ingest(meter=self.meter.pk, energy_kwh=0, power_kw=0, voltage=0)
        self.assertTrue(created)
        reading.refresh_from_db()
        self.assertEqual((reading.energy_kwh, reading.power_kw, reading.voltage), (0, 0, 0))

    def test_missing_meter_is_not_created(self):
        deleted = Meter.objects.create(building=self.building, device_id='DELETED')
        meter_id = deleted.pk
        deleted.delete()
        with self.assertRaises(ValidationError) as error:
            self.ingest(meter=meter_id)
        self.assertIn('meter', error.exception.message_dict)
        self.assertEqual(Meter.objects.count(), 1)
        self.assertFalse(EnergyReading.objects.exists())

    def test_invalid_or_unsaved_meter_identifiers_are_not_coerced(self):
        for meter in [None, True, 'INGEST-MAIN', str(self.meter.pk), float(self.meter.pk),
                      0, -1, Meter(building=self.building, device_id='UNSAVED')]:
            with self.subTest(meter=meter), self.assertRaises(ValidationError):
                self.ingest(meter=meter)
        self.assertFalse(EnergyReading.objects.exists())

    def test_inactive_meter_uses_fresh_database_state_and_retains_history(self):
        existing, _ = self.ingest()
        Meter.objects.filter(pk=self.meter.pk).update(is_active=False)
        # The original Python object still says active: it must not be trusted.
        self.assertTrue(self.meter.is_active)
        for timestamp in [self.timestamp, self.timestamp + timedelta(minutes=1)]:
            with self.subTest(timestamp=timestamp), self.assertRaises(ValidationError) as error:
                self.ingest(timestamp=timestamp)
            self.assertIn('meter', error.exception.message_dict)
        existing.refresh_from_db()
        self.assertEqual(existing.energy_kwh, .1)
        self.assertEqual(EnergyReading.objects.count(), 1)

    def test_invalid_numeric_values_leave_no_rows(self):
        for field in ['energy_kwh', 'power_kw', 'voltage']:
            for value in [-1, float('nan'), float('inf'), -float('inf'), None,
                          'invalid', '0.1', True, False, Decimal('0.1'), 10 ** 400]:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError) as error:
                        self.ingest(**{field: value})
                    self.assertIn(field, error.exception.message_dict)
                    self.assertFalse(EnergyReading.objects.exists())

    def test_invalid_timestamps_are_not_parsed_rounded_or_converted(self):
        for value in [None, '2026-11-09T12:00:00Z', date(2026, 11, 9),
                      self.timestamp.replace(tzinfo=None),
                      self.timestamp.astimezone(timezone(timedelta(hours=1))),
                      self.timestamp + timedelta(seconds=1),
                      self.timestamp + timedelta(microseconds=1)]:
            with self.subTest(timestamp=value), self.assertRaises(ValidationError):
                self.ingest(timestamp=value)
        self.assertFalse(EnergyReading.objects.exists())

    def test_duration_must_be_explicit_integer_60(self):
        for duration in [None, 0, -1, 59, 61, 3600, '60', 60.0, 60.5, True]:
            with self.subTest(duration=duration), self.assertRaises(ValidationError) as error:
                self.ingest(interval_seconds=duration)
            self.assertIn('interval_seconds', error.exception.message_dict)
        self.assertFalse(EnergyReading.objects.exists())

    def test_exact_retry_returns_original_row_and_false(self):
        original, _ = self.ingest()
        retried, created = self.ingest(meter=self.meter.pk, power_kw=9, voltage=230)
        self.assertFalse(created)
        self.assertEqual(retried.pk, original.pk)
        self.assertEqual(EnergyReading.objects.count(), 1)

    def test_conflicting_values_never_overwrite_the_original(self):
        original, _ = self.ingest()
        for field, value in [('energy_kwh', .10000000000000002), ('power_kw', 10), ('voltage', 231)]:
            with self.subTest(field=field), self.assertRaises(ValidationError) as error:
                self.ingest(**{field: value})
            self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'conflicting_reading')
        original.refresh_from_db()
        self.assertEqual((original.interval_seconds, original.energy_kwh, original.power_kw, original.voltage),
                         (60, .1, 9, 230))
        self.assertEqual(EnergyReading.objects.count(), 1)

    def test_same_timestamp_with_different_stored_duration_is_conflict(self):
        for duration in [3600, None]:
            with self.subTest(duration=duration):
                original = self.legacy(duration=duration)
                with self.assertRaises(ValidationError) as error:
                    self.ingest(energy_kwh=6, power_kw=6)
                self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'conflicting_reading')
                original.refresh_from_db()
                self.assertEqual(original.interval_seconds, duration)
                original.delete()

    def test_existing_hourly_interval_overlaps_new_minute(self):
        original = self.legacy(timestamp=self.timestamp - timedelta(minutes=30))
        with self.assertRaises(ValidationError) as error:
            self.ingest()
        self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'overlapping_reading')
        self.assertEqual(EnergyReading.objects.get().pk, original.pk)

    def test_existing_interval_starting_inside_new_minute_also_overlaps(self):
        # Legacy/raw writes can have off-minute starts, unlike this service.
        self.legacy(timestamp=self.timestamp + timedelta(seconds=30), duration=60)
        with self.assertRaises(ValidationError) as error:
            self.ingest()
        self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'overlapping_reading')
        self.assertEqual(EnergyReading.objects.count(), 1)

    def test_adjacent_minutes_and_hourly_boundary_are_allowed(self):
        self.legacy(timestamp=self.timestamp - timedelta(hours=1))
        self.ingest()
        self.ingest(timestamp=self.timestamp + timedelta(minutes=1))
        self.ingest(timestamp=self.timestamp - timedelta(hours=1, minutes=1))
        self.assertEqual(EnergyReading.objects.count(), 4)

    def test_unknown_earlier_duration_blocks_even_very_old_readings(self):
        for offset in [timedelta(minutes=1), timedelta(days=3650)]:
            with self.subTest(offset=offset):
                original = self.legacy(timestamp=self.timestamp - offset, duration=None)
                with self.assertRaises(ValidationError) as error:
                    self.ingest()
                self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'unknown_coverage')
                original.refresh_from_db()
                self.assertIsNone(original.interval_seconds)
                self.assertEqual(EnergyReading.objects.count(), 1)
                original.delete()

    def test_unknown_duration_starting_inside_new_minute_blocks(self):
        self.legacy(timestamp=self.timestamp + timedelta(seconds=30), duration=None)
        with self.assertRaises(ValidationError) as error:
            self.ingest()
        self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'unknown_coverage')

    def test_unknown_duration_starting_at_new_end_cannot_overlap(self):
        self.legacy(timestamp=self.timestamp + timedelta(minutes=1), duration=None)
        reading, created = self.ingest()
        self.assertTrue(created)
        self.assertEqual(reading.interval_seconds, 60)
        self.assertEqual(EnergyReading.objects.count(), 2)

    def test_exact_retry_does_not_add_coverage_even_with_unresolved_legacy_history(self):
        original, _ = self.ingest()
        self.legacy(timestamp=self.timestamp - timedelta(days=1), duration=None)
        retried, created = self.ingest()
        self.assertFalse(created)
        self.assertEqual(retried.pk, original.pk)
        self.assertEqual(EnergyReading.objects.count(), 2)

    def test_no_cross_meter_interference_or_solar_alignment_requirement(self):
        for meter_type in ['ELECTRICITY', 'HVAC', 'LIGHTING', 'SOLAR']:
            meter = Meter.objects.create(building=self.building, device_id=f'OTHER-{meter_type}',
                                         meter_type=meter_type)
            self.legacy(timestamp=self.timestamp - timedelta(hours=1), duration=None, meter=meter)
            reading, created = self.ingest(meter=meter, timestamp=self.timestamp - timedelta(days=1))
            self.assertTrue(created)
            self.assertEqual(reading.meter_id, meter.pk)
        # Other meters' unresolved coverage does not affect this main meter.
        _, created = self.ingest()
        self.assertTrue(created)
        self.assertEqual(Meter.objects.count(), 5)
        self.building.refresh_from_db()
        self.assertIsNone(self.building.has_solar_installation)

    def test_failure_rolls_back_without_hiding_unrelated_database_error(self):
        with patch.object(EnergyReading, 'save', side_effect=IntegrityError('unrelated failure')):
            with self.assertRaisesRegex(IntegrityError, 'unrelated failure'):
                self.ingest()
        self.assertFalse(EnergyReading.objects.exists())
        # The connection/transaction is usable after the failed insertion.
        _, created = self.ingest()
        self.assertTrue(created)


class PostgreSQLIngestionConcurrencyTests(TransactionTestCase):
    """Separate committed connections, never TestCase's wrapping transaction."""

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        building = Building.objects.create(name='Concurrent ingestion laboratory')
        self.meter = Meter.objects.create(building=building, device_id='CONCURRENT-MAIN')
        self.values = dict(meter=self.meter.pk,
            timestamp=datetime(2026, 11, 9, 12, tzinfo=timezone.utc),
            interval_seconds=60, energy_kwh=.1, power_kw=9, voltage=230)

    def worker(self, values, barrier=None, *, bypass=False):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute('SELECT pg_backend_pid()')
                backend_pid = cursor.fetchone()[0]
            if barrier is not None:
                barrier.wait(timeout=10)
            if bypass:
                values = dict(values)
                values['meter_id'] = values.pop('meter')
                row = EnergyReading.objects.create(**values)
                return backend_pid, row.pk, True, None
            try:
                row, created = ingest_reading(**values)
                return backend_pid, row.pk, created, None
            except ValidationError as error:
                return backend_pid, None, None, error.error_dict['timestamp'][0].code
        finally:
            connections['default'].close()

    def concurrent_attempts(self, second_energy):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, dict(self.values, energy_kwh=value), barrier)
                       for value in [.1, second_energy]]
            results = [future.result(timeout=15) for future in futures]
        self.assertNotEqual(results[0][0], results[1][0])
        self.assertEqual(EnergyReading.objects.count(), 1)
        return results

    def test_concurrent_exact_duplicates_create_one_row_and_return_one_retry(self):
        results = self.concurrent_attempts(.1)
        self.assertCountEqual([result[2] for result in results], [True, False])
        self.assertEqual(results[0][1], results[1][1])
        self.assertTrue(all(result[3] is None for result in results))

    def test_concurrent_conflicting_duplicates_preserve_winner(self):
        results = self.concurrent_attempts(.2)
        self.assertEqual(sum(result[2] is True for result in results), 1)
        self.assertEqual(sum(result[3] == 'conflicting_reading' for result in results), 1)
        winner_index = next(i for i, result in enumerate(results) if result[2] is True)
        self.assertEqual(EnergyReading.objects.get().energy_kwh, [.1, .2][winner_index])

    def race_with_bypass_writer(self, energy):
        """Insert on another connection after validation, before the real INSERT.

        This deterministically exercises PostgreSQL uniqueness and savepoint
        recovery, rather than mocking an IntegrityError or relying on timing.
        """
        inserted = False

        def inject(execute, sql, params, many, context):
            nonlocal inserted
            if not inserted and sql.startswith('INSERT INTO "monitoring_energyreading"'):
                inserted = True
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(self.worker, dict(self.values, energy_kwh=energy), bypass=True)
                    result.result(timeout=15)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(inject):
            return ingest_reading(**self.values)

    def test_database_unique_race_recovers_as_exact_retry(self):
        row, created = self.race_with_bypass_writer(.1)
        self.assertFalse(created)
        self.assertEqual(row.pk, EnergyReading.objects.get().pk)

    def test_database_unique_race_reports_conflict_without_overwrite(self):
        with self.assertRaises(ValidationError) as error:
            self.race_with_bypass_writer(.2)
        self.assertEqual(error.exception.error_dict['timestamp'][0].code, 'conflicting_reading')
        self.assertEqual(EnergyReading.objects.get().energy_kwh, .2)
