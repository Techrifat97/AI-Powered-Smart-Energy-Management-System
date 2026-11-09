"""Minute-boundary scheduler for synthetic S1 telemetry."""

from time import sleep
import signal

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from monitoring.services.generator import MINUTE, generate_minute, latest_completed_minute


class Command(BaseCommand):
    help = 'Generate SYNTHETIC 60-second telemetry (not physical measurements); no downtime backfill.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process the latest completed minute and exit.')

    def handle(self, *args, **options):
        def stop(signum, frame):
            # Reuse the Ctrl+C path; atomic building writes unwind on interruption.
            raise KeyboardInterrupt

        previous = signal.signal(signal.SIGTERM, stop)
        self.stdout.write('SYNTHETIC telemetry: UTC minute intervals; no downtime backfill.')
        last_minute = None
        try:
            while True:
                now = timezone.now()
                minute = latest_completed_minute(now)
                if last_minute is None or minute > last_minute:
                    report = generate_minute(minute, now=now)
                    for building in report['buildings']:
                        text = (f"SYNTHETIC building={building['building_id']} minute={minute.isoformat()} "
                                f"status={building['status']} created={building['created']} "
                                f"already_existing={building['already_existing']} "
                                f"skipped_meter_ids={building['skipped_meter_ids']} reason={building['reason']}")
                        stream = self.stderr if building['status'] == 'failed' else self.stdout
                        stream.write(text)
                    self.stdout.write(
                        f"SYNTHETIC cycle={minute.isoformat()} created={report['created']} "
                        f"already_existing={report['already_existing']} "
                        f"skipped_buildings={report['skipped']} failed_buildings={report['failed']}")
                    last_minute = minute
                    if options['once']:
                        if report['failed']:
                            raise CommandError('Synthetic cycle finished with failed buildings; see reasons above.')
                        return
                # Recalculate from the wall clock AFTER processing. Work duration
                # is not added to a fixed 60-second sleep. Missed minutes are dropped.
                after = timezone.now()
                boundary = after.replace(second=0, microsecond=0) + MINUTE
                sleep((boundary - after).total_seconds())
        except KeyboardInterrupt:
            self.stdout.write('Stopped synthetic telemetry.')
        except DatabaseError as error:
            # Stop, rather than spinning/retrying on an unavailable database.
            # --traceback retains the cause for diagnosis without printing local
            # connection details in the ordinary CLI error message.
            raise CommandError(
                f'PostgreSQL operation failed ({type(error).__name__}); synthetic worker stopped. '
                'Check database availability; use --traceback for details.'
            ) from error
        finally:
            signal.signal(signal.SIGTERM, previous)
