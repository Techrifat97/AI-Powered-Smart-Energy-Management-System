"""Synthetic building-minute contracts, using disposable PostgreSQL data only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase

from monitoring.models import Building, EnergyReading, Meter
from monitoring.services.aggregation import summarize_building
from monitoring.services.generator import generate_minute, latest_completed_minute
from monitoring.services.ingestion import ingest_reading


class GeneratorFixtures:
    def setUp(self):
        super().setUp()
        self.minute = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        self.now = self.minute + timedelta(minutes=1, seconds=20)
        self.serial = 0

    def meter(self, building, kind, *, created_at=None, active=True):
        self.serial += 1
        with patch('django.utils.timezone.now', return_value=created_at or self.minute - timedelta(days=1)):
            return Meter.objects.create(building=building, device_id=f'GEN-{self.serial}',
                                        meter_type=kind, is_active=active)

    def building(self, *, solar=False):
        building = Building.objects.create(name='Synthetic laboratory', has_solar_installation=solar)
        meters = {kind: self.meter(building, kind) for kind in ['ELECTRICITY', 'HVAC', 'LIGHTING']}
        if solar:
            meters['SOLAR'] = self.meter(building, 'SOLAR')
        return building, meters

    def cycle(self, minute=None):
        minute = self.minute if minute is None else minute
        return generate_minute(minute, now=minute + timedelta(minutes=1, seconds=20))

    def outcome(self, report, building):
        return next(row for row in report['buildings'] if row['building_id'] == building.pk)


class GeneratorTests(GeneratorFixtures, TestCase):
    def test_latest_completed_utc_minute(self):
        for second in [0, 1, 59]:
            self.assertEqual(latest_completed_minute(self.now.replace(second=second)), self.minute)
        self.assertEqual(latest_completed_minute(self.minute), self.minute - timedelta(minutes=1))
        for invalid in [None, '2026-11-09', self.now.replace(tzinfo=None),
                        self.now.astimezone(timezone(timedelta(hours=1)))]:
            if invalid is None:  # The omitted/default clock uses timezone.now().
                with patch('monitoring.services.generator.timezone.now', return_value=self.now):
                    self.assertEqual(latest_completed_minute(), self.minute)
            else:
                with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                    latest_completed_minute(invalid)

    def test_unfinished_future_and_invalid_interval_starts_are_rejected(self):
        self.building()
        for minute in [self.minute + timedelta(minutes=1), self.minute + timedelta(days=1),
                       self.minute + timedelta(seconds=1), self.minute.replace(tzinfo=None),
                       self.minute.astimezone(timezone(timedelta(hours=1)))]:
            with self.subTest(minute=minute), self.assertRaises(ValidationError):
                generate_minute(minute, now=self.now)
        self.assertFalse(EnergyReading.objects.exists())

    def test_complete_set_has_consistent_submeters_separate_solar_and_duration(self):
        building, meters = self.building(solar=True)
        self.meter(building, 'HVAC')
        self.meter(building, 'LIGHTING')
        report = self.cycle()
        self.assertEqual(report['created'], 6)
        rows = list(EnergyReading.objects.select_related('meter'))
        main = next(r for r in rows if r.meter_id == meters['ELECTRICITY'].pk)
        sub = [r for r in rows if r.meter.meter_type in ('HVAC', 'LIGHTING')]
        solar = next(r for r in rows if r.meter_id == meters['SOLAR'].pk)
        self.assertLessEqual(sum(r.energy_kwh for r in sub), main.energy_kwh)
        self.assertLessEqual(sum(r.power_kw for r in sub), main.power_kw)
        self.assertEqual(solar.power_kw, 10)  # Documented synthetic noon peak.
        self.assertGreaterEqual(main.power_kw, 12)
        self.assertLess(main.power_kw, 13)
        for row in rows:
            self.assertEqual(row.timestamp, self.minute)
            self.assertEqual(row.timestamp.utcoffset(), timedelta(0))
            self.assertEqual(row.interval_seconds, 60)
            self.assertEqual(row.energy_kwh, row.power_kw / 60)
            self.assertEqual(row.voltage, 230)
        summary = summarize_building(building)
        self.assertEqual(summary['total_consumption_kwh'], main.energy_kwh)
        self.assertEqual(summary['total_solar_generated_kwh'], solar.energy_kwh)
        self.assertTrue(summary['grid_estimates_available'])

    def test_night_solar_is_recorded_zero_not_missing(self):
        building, meters = self.building(solar=True)
        self.cycle(self.minute.replace(hour=23))
        solar = meters['SOLAR'].readings.get()
        self.assertEqual((solar.energy_kwh, solar.power_kw), (0, 0))
        self.assertEqual(EnergyReading.objects.count(), 4)
        self.assertTrue(summarize_building(building)['solar_data_available'])

    def test_confirmed_no_solar_generates_only_load_meters(self):
        building, _ = self.building()
        report = self.cycle()
        self.assertEqual(report['created'], 3)
        self.assertFalse(EnergyReading.objects.filter(meter__meter_type='SOLAR').exists())
        building.refresh_from_db()
        self.assertIs(building.has_solar_installation, False)

    def test_actual_once_command_generates_only_latest_minute_on_disposable_data(self):
        self.building(solar=True)
        output = StringIO()
        with patch('monitoring.management.commands.run_telemetry.timezone.now', return_value=self.now):
            call_command('run_telemetry', once=True, stdout=output)
            call_command('run_telemetry', once=True, stdout=output)
        self.assertEqual(EnergyReading.objects.count(), 4)
        self.assertEqual(set(EnergyReading.objects.values_list('timestamp', flat=True)), {self.minute})
        self.assertIn('created=4', output.getvalue())
        self.assertIn('already_existing=4', output.getvalue())

    def test_weekend_and_sunrise_profile_are_explicit(self):
        _, meters = self.building(solar=True)
        saturday = self.minute + timedelta(days=5)
        self.cycle(saturday)
        self.assertGreaterEqual(meters['ELECTRICITY'].readings.get().power_kw, 8)
        self.assertLess(meters['ELECTRICITY'].readings.get().power_kw, 9)
        for hour, expected in [(6, 0), (9, 5), (18, 0)]:
            minute = saturday.replace(hour=hour)
            self.cycle(minute)
            self.assertEqual(meters['SOLAR'].readings.get(timestamp=minute).power_kw, expected)

    def test_unknown_contradictory_and_unsupported_inventories_are_skipped(self):
        cases = ['unknown', 'missing_main', 'two_mains', 'two_solar', 'missing_solar',
                 'inactive_solar', 'false_active_solar', 'false_inactive_solar']
        expected = ['unknown_solar_installation', 'requires_exactly_one_active_main',
                    'requires_exactly_one_active_main', 'multiple_active_solar_meters_unsupported',
                    'installed_solar_requires_one_active_solar_meter',
                    'installed_solar_requires_one_active_solar_meter',
                    'no_solar_metadata_conflicts_with_configured_solar_meter',
                    'no_solar_metadata_conflicts_with_configured_solar_meter']
        buildings = []
        for case in cases:
            building, meters = self.building(solar=case in ['two_solar', 'inactive_solar',
                                                          'false_active_solar', 'false_inactive_solar'])
            if case == 'unknown':
                building.has_solar_installation = None
            elif case == 'missing_main':
                Meter.objects.filter(pk=meters['ELECTRICITY'].pk).update(is_active=False)
            elif case == 'two_mains':
                self.meter(building, 'ELECTRICITY')
            elif case == 'two_solar':
                self.meter(building, 'SOLAR')
            elif case == 'missing_solar':
                building.has_solar_installation = True
            elif case == 'inactive_solar':
                Meter.objects.filter(pk=meters['SOLAR'].pk).update(is_active=False)
            elif case.startswith('false_'):
                building.has_solar_installation = False
                if case == 'false_inactive_solar':
                    Meter.objects.filter(pk=meters['SOLAR'].pk).update(is_active=False)
            building.save()
            buildings.append(building)
        report = self.cycle()
        self.assertEqual(report['skipped'], len(cases))
        self.assertEqual(report['failed'], 0)
        for case, building, reason in zip(cases, buildings, expected):
            with self.subTest(case=case):
                self.assertEqual(self.outcome(report, building)['reason'], reason)
                flag = building.has_solar_installation
                building.refresh_from_db()
                self.assertEqual(building.has_solar_installation, flag)
        self.assertFalse(EnergyReading.objects.exists())

    def test_new_submeter_joins_next_eligible_minute_not_before_creation(self):
        building, _ = self.building()
        new_meter = self.meter(building, 'HVAC', created_at=self.minute + timedelta(seconds=30))
        report = self.cycle()
        self.assertEqual(report['created'], 3)
        self.assertEqual(self.outcome(report, building)['skipped_meter_ids'], [new_meter.pk])
        self.assertFalse(new_meter.readings.exists())
        report = self.cycle(self.minute + timedelta(minutes=1))
        self.assertEqual(report['created'], 4)
        self.assertEqual(new_meter.readings.get().timestamp, self.minute + timedelta(minutes=1))

    def test_new_required_main_delays_complete_building_until_eligible(self):
        building, meters = self.building()
        Meter.objects.filter(pk=meters['ELECTRICITY'].pk).update(created_at=self.minute + timedelta(seconds=30))
        report = self.cycle()
        self.assertEqual(self.outcome(report, building)['reason'], 'required_meter_created_after_interval_start')
        self.assertFalse(EnergyReading.objects.exists())
        self.assertEqual(self.cycle(self.minute + timedelta(minutes=1))['created'], 3)

    def test_new_required_solar_delays_whole_set(self):
        building, meters = self.building(solar=True)
        Meter.objects.filter(pk=meters['SOLAR'].pk).update(created_at=self.minute + timedelta(seconds=30))
        self.assertEqual(self.cycle()['skipped'], 1)
        self.assertFalse(EnergyReading.objects.exists())
        self.assertEqual(self.cycle(self.minute + timedelta(minutes=1))['created'], 4)

    def test_inventory_is_requeried_for_activation_and_deactivation(self):
        building, meters = self.building()
        hvac = meters['HVAC']
        Meter.objects.filter(pk=hvac.pk).update(is_active=False)
        self.assertEqual(self.cycle()['created'], 2)
        Meter.objects.filter(pk=hvac.pk).update(is_active=True)
        self.assertEqual(self.cycle(self.minute + timedelta(minutes=1))['created'], 3)
        old = list(hvac.readings.values_list('pk', 'timestamp', 'energy_kwh'))
        Meter.objects.filter(pk=hvac.pk).update(is_active=False)
        self.assertEqual(self.cycle(self.minute + timedelta(minutes=2))['created'], 2)
        self.assertEqual(list(hvac.readings.values_list('pk', 'timestamp', 'energy_kwh')), old)

    def test_new_building_is_discovered_without_restart(self):
        self.assertEqual(self.cycle()['created'], 0)
        building, _ = self.building()
        # Assets appear after the preceding cycle, during the next interval.
        created = self.minute + timedelta(minutes=1, seconds=30)
        Building.objects.filter(pk=building.pk).update(created_at=created)
        building.meters.update(created_at=created)
        report = self.cycle(self.minute + timedelta(minutes=2))
        self.assertEqual(self.outcome(report, building)['created'], 3)
        self.assertEqual(Building.objects.count(), 1)
        self.assertEqual(Meter.objects.count(), 3)

    def test_retry_is_deterministic_and_preserves_every_stored_value(self):
        self.building(solar=True)
        self.assertEqual(self.cycle()['created'], 4)
        before = list(EnergyReading.objects.order_by('pk').values())
        report = self.cycle()
        self.assertEqual(report['created'], 0)
        self.assertEqual(report['already_existing'], 4)
        self.assertEqual(report['failed'], 0)
        self.assertEqual(list(EnergyReading.objects.order_by('pk').values()), before)

    def test_partial_existing_cycle_is_preserved_and_not_filled(self):
        building, meters = self.building()
        ingest_reading(meters['ELECTRICITY'], timestamp=self.minute, interval_seconds=60,
                      energy_kwh=.1, power_kw=9, voltage=230)
        before = list(EnergyReading.objects.values())
        report = self.cycle()
        self.assertEqual(self.outcome(report, building)['status'], 'failed')
        self.assertIn('partial or changed meter set', self.outcome(report, building)['reason'])
        self.assertEqual(list(EnergyReading.objects.values()), before)

    def test_added_eligible_meter_on_retry_reports_changed_set(self):
        building, _ = self.building()
        self.cycle()
        new_meter = self.meter(building, 'HVAC')
        report = self.cycle()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(EnergyReading.objects.count(), 3)
        self.assertFalse(new_meter.readings.exists())

    def test_removed_active_meter_on_retry_preserves_old_set_and_reports_conflict(self):
        building, meters = self.building()
        self.cycle()
        before = list(EnergyReading.objects.order_by('pk').values())
        Meter.objects.filter(pk=meters['HVAC'].pk).update(is_active=False)
        report = self.cycle()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(list(EnergyReading.objects.order_by('pk').values()), before)

    def test_conflicting_complete_set_is_not_overwritten(self):
        building, meters = self.building()
        self.cycle()
        meters['LIGHTING'].readings.update(energy_kwh=99)
        before = list(EnergyReading.objects.order_by('pk').values())
        report = self.cycle()
        self.assertEqual(self.outcome(report, building)['status'], 'failed')
        self.assertIn('different measurements', self.outcome(report, building)['reason'])
        self.assertEqual(list(EnergyReading.objects.order_by('pk').values()), before)

    def test_overlap_failure_rolls_back_new_members_and_other_building_continues(self):
        bad, meters = self.building()
        good, _ = self.building(solar=True)
        old = EnergyReading.objects.create(meter=meters['LIGHTING'],
            timestamp=self.minute - timedelta(minutes=30), interval_seconds=3600,
            energy_kwh=6, power_kw=6, voltage=230)
        report = self.cycle()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['created'], 4)
        self.assertIn('overlaps', self.outcome(report, bad)['reason'])
        self.assertEqual(self.outcome(report, good)['status'], 'created')
        self.assertFalse(EnergyReading.objects.filter(meter__building=bad, timestamp=self.minute).exists())
        old.refresh_from_db()
        self.assertEqual((old.interval_seconds, old.energy_kwh), (3600, 6))

    def test_unknown_duration_failure_rolls_back_building_without_guessing(self):
        building, meters = self.building()
        old = EnergyReading.objects.create(meter=meters['HVAC'], timestamp=self.minute - timedelta(days=365),
                                          interval_seconds=None, energy_kwh=6, power_kw=6)
        report = self.cycle()
        self.assertEqual(self.outcome(report, building)['status'], 'failed')
        self.assertIn('unknown duration', self.outcome(report, building)['reason'])
        self.assertEqual(EnergyReading.objects.count(), 1)
        old.refresh_from_db()
        self.assertIsNone(old.interval_seconds)

    def test_bad_inventory_does_not_stop_valid_building(self):
        bad, _ = self.building()
        good, _ = self.building()
        Building.objects.filter(pk=bad.pk).update(has_solar_installation=None)
        report = self.cycle()
        self.assertEqual(report['skipped'], 1)
        self.assertEqual(self.outcome(report, good)['created'], 3)

    def test_unexpected_failure_and_interrupt_roll_back_current_building_and_propagate(self):
        self.building()
        for failure in [RuntimeError('unexpected'), KeyboardInterrupt()]:
            calls = 0

            def ingest(**values):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise failure
                return ingest_reading(**values)

            with self.subTest(failure=type(failure).__name__):
                with patch('monitoring.services.generator.ingest_reading', side_effect=ingest):
                    with self.assertRaises(type(failure)):
                        self.cycle()
                self.assertFalse(EnergyReading.objects.exists())


class GeneratorConcurrencyTests(GeneratorFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql')
        self.building_row, self.meters = self.building(solar=True)

    def worker(self, barrier, *, single=False):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            barrier.wait(timeout=10)
            if single:
                try:
                    ingest_reading(self.meters['ELECTRICITY'].pk, timestamp=self.minute,
                        interval_seconds=60, energy_kwh=.1, power_kw=9, voltage=230)
                    return pid, 'created'
                except ValidationError:
                    return pid, 'conflict'
            return pid, self.cycle()
        finally:
            connections['default'].close()

    def test_simultaneous_generators_create_one_complete_set_and_one_retry(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, barrier) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertNotEqual(results[0][0], results[1][0])
        self.assertCountEqual([r[1]['created'] for r in results], [4, 0])
        self.assertCountEqual([r[1]['already_existing'] for r in results], [0, 4])
        self.assertTrue(all(r[1]['failed'] == 0 for r in results))
        self.assertEqual(EnergyReading.objects.count(), 4)

    def test_generator_and_conflicting_ingestion_have_no_partial_new_generator_set(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            generator = pool.submit(self.worker, barrier)
            single = pool.submit(self.worker, barrier, single=True)
            report = generator.result(timeout=15)[1]
            ingestion = single.result(timeout=15)[1]
        if ingestion == 'created':
            self.assertEqual(report['failed'], 1)
            self.assertEqual(EnergyReading.objects.count(), 1)
            self.assertEqual(EnergyReading.objects.get().energy_kwh, .1)
        else:
            self.assertEqual(report['created'], 4)
            self.assertEqual(EnergyReading.objects.count(), 4)
