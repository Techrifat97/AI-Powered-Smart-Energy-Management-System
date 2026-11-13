"""Explicit synthetic demo initialization. Never repairs or overwrites existing data."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from monitoring.models import Building, Meter, EnergyReading, DemoDataset
from monitoring.services.inventory import save_building, save_meter

DEMO_NAME = 'Docker demo'
SPECS = {'DOCKER-DEMO-MAIN': 'ELECTRICITY', 'DOCKER-DEMO-HVAC': 'HVAC',
         'DOCKER-DEMO-LIGHTING': 'LIGHTING', 'DOCKER-DEMO-SOLAR': 'SOLAR'}
DATASET_KEY = 'capstone-demo-v1'


def _serialize_setup():
    # A row cannot be locked before it exists. Serialize cooperating bootstrap jobs.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [71310261])


@transaction.atomic
def ensure_inventory():
    """Return (building, created), recognizing reserved device IDs before names."""
    _serialize_setup()
    reserved = list(Meter.objects.filter(device_id__in=SPECS).order_by('pk'))
    if reserved:
        owners = {m.building_id for m in reserved}
        if len(reserved) != 4 or len(owners) != 1:
            # Preserve the old command's useful diagnostic for partial name matches.
            message = 'incompatible' if Building.objects.filter(name=DEMO_NAME).exists() else 'assigned elsewhere'
            raise ValidationError(f'Demo device IDs are {message}; nothing was changed.')
        building = Building.objects.select_for_update().get(pk=owners.pop())
    else:
        matches = list(Building.objects.select_for_update().filter(name=DEMO_NAME))
        if len(matches) > 1:
            raise ValidationError('Multiple Docker demo buildings exist; review inventory.')
        if matches:
            building = matches[0]
        else:
            building = save_building(dict(name=DEMO_NAME, has_solar_installation=True))
            for device_id, kind in SPECS.items():
                save_meter(dict(device_id=device_id, meter_type=kind), building_id=building.pk)
            return building, True
    meters = list(Meter.objects.select_for_update(no_key=True).filter(building=building).order_by('pk'))
    if (building.has_solar_installation is not True
            or {m.device_id: m.meter_type for m in meters} != SPECS
            or any(not m.is_active or m.unit != 'kWh' for m in meters)):
        raise ValidationError('Existing Docker demo inventory is incompatible; nothing was changed.')
    return building, False


@transaction.atomic
def bootstrap_demo(*, now=None, refresh=False):
    """Initialize only an empty dedicated inventory; repeated calls are read-only.

    Existing readings without our marker are adopted without guessed coverage or
    backfill. A renamed building is recognized by stable device IDs. Normal API
    building creation never invokes this function.
    """
    _serialize_setup()
    _ensure_demo_user()
    marker = DemoDataset.objects.select_related('building').filter(pk=DATASET_KEY).first()
    if marker:
        if refresh:
            return _refresh_history(marker.building, now or timezone.now())
        return dict(status='already_initialized', building_id=marker.building_id, created=0)
    building, _ = ensure_inventory()
    if EnergyReading.objects.filter(meter__building=building).exists():
        tariff_status = _ensure_demo_tariff()
        DemoDataset.objects.create(key=DATASET_KEY, building=building)
        return dict(status='adopted_existing_history_without_backfill', building_id=building.pk,
                    created=0, tariff_status=tariff_status)
    now = now or timezone.now()
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=14)
    meters = list(building.meters.order_by('pk'))
    rows = _history_rows(building, meters, start, end)
    EnergyReading.objects.bulk_create(rows)
    tariff_status = _ensure_demo_tariff()
    DemoDataset.objects.create(key=DATASET_KEY, building=building,
                               history_start=start.date(), history_end=(end - timedelta(days=1)).date())
    return dict(status='initialized', building_id=building.pk, created=len(rows), tariff_status=tariff_status,
                period_start=start.date().isoformat(), period_end=(end - timedelta(days=1)).date().isoformat())


def _history_rows(building, meters, start, end):
    from monitoring.services.profiles import TelemetryGenerator
    simulator = TelemetryGenerator()
    rows = []
    hour = start
    while hour < end:
        for values in simulator.iter_readings(building, meters, hour, interval_seconds=3600):
            row = EnergyReading(**values)
            row.full_clean(validate_unique=False, validate_constraints=False)
            rows.append(row)
        hour += timedelta(hours=1)
    return rows


def _refresh_history(building, now):
    """Explicit demo-only refresh: fill wholly empty days, skip any existing coverage."""
    from django.db.models import DateTimeField, ExpressionWrapper, F
    verified, _ = ensure_inventory()
    if verified.pk != building.pk:
        raise ValidationError('Stable demo identity conflicts with reserved inventory; refresh skipped.')
    meters = list(Meter.objects.select_for_update(no_key=True).filter(building=building).order_by('pk'))
    readings = EnergyReading.objects.filter(meter__building=building)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    interval_end = ExpressionWrapper(F('timestamp') + F('interval_seconds') * timedelta(seconds=1),
                                     output_field=DateTimeField())
    created, skipped = 0, []
    for offset in range(14, 0, -1):
        start = end - timedelta(days=offset)
        stop = start + timedelta(days=1)
        if (readings.filter(timestamp__gte=start,timestamp__lt=stop).exists()
                or readings.filter(timestamp__lt=stop,interval_seconds__isnull=True).exists()
                or readings.filter(timestamp__lt=start).annotate(interval_end=interval_end).filter(interval_end__gt=start).exists()):
            skipped.append(start.date().isoformat())
            continue
        rows = _history_rows(building, meters, start, stop)
        EnergyReading.objects.bulk_create(rows)
        created += len(rows)
    return dict(status='refreshed_empty_days_only', building_id=building.pk, created=created,
                skipped_days=skipped)


def _ensure_demo_tariff():
    from analysis.models import TariffPlan
    active_count = TariffPlan.objects.filter(is_active=True).count()
    if active_count:
        return 'preserved_active_tariff' if active_count == 1 else 'ambiguous_existing_active_tariffs'
    TariffPlan.objects.create(name='Synthetic demo flat tariff', rate_standard_eur_per_kwh=.30,
                              rate_peak_eur_per_kwh=.30, solar_feed_in_eur_per_kwh=.08)
    return 'created_demo_tariff'


def _ensure_demo_user():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@smartenergy.local',
            'is_staff': True,
            'is_superuser': True,
        }
    )
    if created:
        user.set_password('admin123')
        user.save()
        return 'created_demo_admin'
    return 'preserved_demo_admin'
