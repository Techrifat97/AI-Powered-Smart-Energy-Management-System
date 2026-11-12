"""Opt-in demo startup; production mode never fabricates historical readings."""
import os
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from monitoring.services.demo import bootstrap_demo


class Command(BaseCommand):
    help = 'Safely initialize 14 complete previous UTC days when SMART_ENERGY_DEMO=true.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true', help='Explicitly fill only wholly empty recent demo days.')

    def handle(self, *args, **options):
        if os.environ.get('SMART_ENERGY_DEMO', 'false').lower() != 'true':
            self.stdout.write('Demo bootstrap disabled; no historical data generated.')
            return
        try:
            self.stdout.write(str(bootstrap_demo(refresh=options['refresh'])))
        except ValidationError as error:
            # Existing incompatible records must not prevent the user's backend
            # from starting. Telemetry independently rejects invalid inventories.
            self.stderr.write('Demo bootstrap skipped: ' + '; '.join(error.messages))
