"""Explicit, repeatable setup; never called automatically at container startup."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from monitoring.models import Building, Meter
from monitoring.services.inventory import save_building, save_meter


DEMO_NAME = 'Docker demo'
SPECS = {
    'DOCKER-DEMO-MAIN': 'ELECTRICITY',
    'DOCKER-DEMO-HVAC': 'HVAC',
    'DOCKER-DEMO-LIGHTING': 'LIGHTING',
    'DOCKER-DEMO-SOLAR': 'SOLAR',
}


class Command(BaseCommand):
    help = 'Explicitly create or verify one synthetic demo building and four active meters; never overwrite.'

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                matches = list(Building.objects.select_for_update().filter(name=DEMO_NAME).order_by('pk'))
                if len(matches) > 1:
                    raise CommandError('Multiple Docker demo buildings exist; review inventory before setup.')
                if matches:
                    building = matches[0]
                    meters = list(Meter.objects.select_for_update(no_key=True).filter(
                        building=building).order_by('pk'))
                    if (building.has_solar_installation is not True
                            or {m.device_id: m.meter_type for m in meters} != SPECS
                            or any(not m.is_active or m.unit != 'kWh' for m in meters)):
                        raise CommandError('Existing Docker demo inventory is incompatible; nothing was changed.')
                    created = False
                else:
                    if Meter.objects.filter(device_id__in=SPECS).exists():
                        raise CommandError('Demo device IDs are already assigned elsewhere; nothing was changed.')
                    building = save_building(dict(name=DEMO_NAME, has_solar_installation=True))
                    for device_id, meter_type in SPECS.items():
                        save_meter(dict(device_id=device_id, meter_type=meter_type), building_id=building.pk)
                    created = True
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        action = 'Created' if created else 'Verified existing'
        self.stdout.write(f'{action} SYNTHETIC demo building id={building.pk} with four active meters. '
                          'Meters first qualify after a completed interval starts after their creation.')
