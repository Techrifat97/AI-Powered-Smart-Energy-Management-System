"""Small management write operations; generator-compatible inventory locking."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from monitoring.models import Building, EnergyReading, Meter


def _locked_inventory(building_id):
    # Call only inside atomic(). Match the generator: building, then meters by PK.
    building = get_object_or_404(Building.objects.select_for_update(), pk=building_id)
    meters = list(Meter.objects.select_for_update(no_key=True).filter(
        building=building).order_by('pk'))
    return building, meters


def _clean_save(instance):
    instance.full_clean()
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as error:
        constraint = getattr(getattr(error.__cause__, 'diag', None), 'constraint_name', None)
        if isinstance(instance, Meter) and constraint == 'monitoring_meter_device_id_key':
            raise ValidationError({'device_id': 'A meter with this device ID already exists.'}) from None
        raise
    return instance


def save_building(attributes, *, building_id=None):
    """Create/update descriptive fields; changing solar meaning requires no history."""
    with transaction.atomic():
        if building_id is None:
            building = Building(**attributes)
        else:
            building, meters = _locked_inventory(building_id)
            solar = attributes.get('has_solar_installation', building.has_solar_installation)
            if solar != building.has_solar_installation:
                if EnergyReading.objects.filter(meter__building=building).exists():
                    raise ValidationError({'has_solar_installation':
                        'Solar status cannot change after readings exist. Historical corrections require review.'})
                if solar is False and any(m.meter_type == 'SOLAR' for m in meters):
                    raise ValidationError({'has_solar_installation':
                        'Solar meters are configured, including inactive devices; absence cannot be declared.'})
            for field, value in attributes.items():
                setattr(building, field, value)
        return _clean_save(building)


def save_meter(attributes, *, building_id, meter_id=None):
    """Create a meter, or change only is_active, under a locked fresh inventory.

    API serializers enforce writable fields. Temporary missing required meters
    are allowed. These checks are not database constraints on bypass writers.
    """
    with transaction.atomic():
        building, meters = _locked_inventory(building_id)
        if meter_id is None:
            meter = Meter(building=building, **attributes)
        else:
            meter = next((m for m in meters if m.pk == meter_id), None)
            if meter is None:
                raise ValidationError({'is_active': 'The meter inventory changed; reload the meter.'})
            meter.is_active = attributes['is_active']
        if meter.meter_type == 'SOLAR' and (meter_id is None or meter.is_active):
            if building.has_solar_installation is not True:
                raise ValidationError({'meter_type' if meter_id is None else 'is_active':
                    'Solar creation/activation requires has_solar_installation=true.'})
        if meter.is_active and meter.meter_type in ('ELECTRICITY', 'SOLAR'):
            if any(m.pk != meter.pk and m.is_active and m.meter_type == meter.meter_type for m in meters):
                raise ValidationError({'is_active':
                    f'This building already has an active {meter.meter_type} meter; deactivate it first.'})
        return _clean_save(meter)
