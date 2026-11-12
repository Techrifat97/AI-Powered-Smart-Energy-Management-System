"""Explicit inventory-only setup; stable device IDs survive building renames."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from monitoring.services.demo import DEMO_NAME, SPECS, ensure_inventory


class Command(BaseCommand):
    help = 'Create or verify dedicated synthetic demo inventory; never overwrite or seed history.'

    def handle(self, *args, **options):
        try:
            building, created = ensure_inventory()
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write(f"{'Created' if created else 'Verified existing'} SYNTHETIC demo building id={building.pk} with four active meters.")
