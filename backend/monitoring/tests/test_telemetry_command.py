"""Controlled-clock scheduler tests: no real waits and no application DB access."""

from datetime import datetime, timedelta, timezone
from io import StringIO
import signal
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import OperationalError
from django.test import SimpleTestCase


COMMAND = 'monitoring.management.commands.run_telemetry'


class TelemetryCommandTests(SimpleTestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 9, 12, 1, 10, tzinfo=timezone.utc)]
        self.stdout, self.stderr = StringIO(), StringIO()
        self.report = dict(created=3, already_existing=0, skipped=0, failed=0, buildings=[
            dict(building_id=1, status='created', created=3, already_existing=0,
                 skipped_meter_ids=[], reason=''),
        ])

    def run_command(self, **options):
        call_command('run_telemetry', stdout=self.stdout, stderr=self.stderr, **options)

    def test_once_processes_only_latest_completed_minute_and_never_sleeps(self):
        with patch(f'{COMMAND}.timezone.now', side_effect=lambda: self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report) as generate:
                with patch(f'{COMMAND}.sleep') as sleep:
                    self.run_command(once=True)
        generate.assert_called_once_with(self.clock[0].replace(minute=0, second=0), now=self.clock[0])
        sleep.assert_not_called()
        self.assertIn('SYNTHETIC', self.stdout.getvalue())
        self.assertIn('created=3', self.stdout.getvalue())

    def test_boundary_scheduling_subtracts_work_time_instead_of_sleeping_60(self):
        waits = []

        def generate(*args, **kwargs):
            self.clock[0] += timedelta(seconds=7)
            return self.report

        def sleep(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                raise KeyboardInterrupt
            self.clock[0] += timedelta(seconds=seconds)

        with patch(f'{COMMAND}.timezone.now', side_effect=lambda: self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', side_effect=generate) as generate_mock:
                with patch(f'{COMMAND}.sleep', side_effect=sleep):
                    self.run_command()
        self.assertEqual(waits, [43, 53])
        self.assertEqual([c.args[0].minute for c in generate_mock.call_args_list], [0, 1])
        self.assertIn('Stopped synthetic telemetry.', self.stdout.getvalue())

    def test_clock_jump_or_downtime_does_not_backfill_missed_minutes(self):
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                raise KeyboardInterrupt
            self.clock[0] += timedelta(seconds=seconds, minutes=10)

        with patch(f'{COMMAND}.timezone.now', side_effect=lambda: self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report) as generate:
                with patch(f'{COMMAND}.sleep', side_effect=sleep):
                    self.run_command()
        self.assertEqual([c.args[0].minute for c in generate.call_args_list], [0, 11])
        self.assertEqual(generate.call_count, 2)

    def test_backward_clock_does_not_replay_an_older_minute(self):
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                raise KeyboardInterrupt
            self.clock[0] -= timedelta(minutes=1)

        with patch(f'{COMMAND}.timezone.now', side_effect=lambda: self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report) as generate:
                with patch(f'{COMMAND}.sleep', side_effect=sleep):
                    self.run_command()
        generate.assert_called_once()
        self.assertEqual(waits, [50, 50])

    def test_interrupt_during_work_is_clean(self):
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', side_effect=KeyboardInterrupt):
                self.run_command()
        self.assertIn('Stopped synthetic telemetry.', self.stdout.getvalue())

    def test_sigterm_stops_cleanly_and_restores_the_previous_handler(self):
        previous = signal.getsignal(signal.SIGTERM)
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report):
                with patch(f'{COMMAND}.sleep', side_effect=lambda seconds: signal.raise_signal(signal.SIGTERM)):
                    self.run_command()
        self.assertIn('Stopped synthetic telemetry.', self.stdout.getvalue())
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_unavailable_database_stops_without_retry_loop(self):
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', side_effect=OperationalError('unavailable')) as generate:
                with patch(f'{COMMAND}.sleep') as sleep:
                    with self.assertRaisesRegex(CommandError, 'worker stopped'):
                        self.run_command()
        generate.assert_called_once()
        sleep.assert_not_called()

    def test_unexpected_errors_are_not_concealed(self):
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', side_effect=RuntimeError('unexpected')):
                with self.assertRaisesRegex(RuntimeError, 'unexpected'):
                    self.run_command()

    def test_once_reports_failure_and_exits_with_command_error(self):
        self.report.update(created=0, failed=1)
        self.report['buildings'][0].update(status='failed', created=0, reason='unknown duration')
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report):
                with self.assertRaisesRegex(CommandError, 'failed buildings'):
                    self.run_command(once=True)
        self.assertIn('unknown duration', self.stderr.getvalue())
        self.assertIn('failed_buildings=1', self.stdout.getvalue())

    def test_inventory_skip_is_reported_without_a_database_write_attempt(self):
        self.report.update(created=0, skipped=1)
        self.report['buildings'][0].update(status='skipped', created=0, reason='unknown_solar_installation')
        with patch(f'{COMMAND}.timezone.now', return_value=self.clock[0]):
            with patch(f'{COMMAND}.generate_minute', return_value=self.report):
                self.run_command(once=True)
        self.assertIn('unknown_solar_installation', self.stdout.getvalue())
        self.assertIn('skipped_buildings=1', self.stdout.getvalue())
