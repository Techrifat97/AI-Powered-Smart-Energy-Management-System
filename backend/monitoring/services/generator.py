"""Deterministic SYNTHETIC telemetry; these are not physical measurements."""

from datetime import datetime, timedelta
from hashlib import sha256

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from monitoring.models import Building, EnergyReading, Meter
from monitoring.services.ingestion import ingest_reading
from monitoring.validators import validate_interval_timestamp


MINUTE = timedelta(minutes=1)


def latest_completed_minute(now=None):
    """At 12:01 (or 12:01:59) UTC return 12:00, never the unfinished minute."""
    now = timezone.now() if now is None else now
    if not isinstance(now, datetime) or timezone.is_naive(now) or now.utcoffset() != timedelta(0):
        raise ValidationError('The cycle clock must be a timezone-aware UTC datetime.')
    return now.replace(second=0, microsecond=0) - MINUTE


def _result(building_id, status, reason='', *, created=0, already_existing=0, skipped_meter_ids=()):
    return dict(building_id=building_id, status=status, reason=reason, created=created,
                already_existing=already_existing, skipped_meter_ids=list(skipped_meter_ids))


def _plan(building, meters, minute):
    """Integer-watt profile v1; category budgets bound combined submeter load."""
    fingerprint = ','.join(f'{m.pk}:{m.meter_type}:{m.device_id}' for m in meters)
    seed = f's1-synthetic-v1|{building.pk}|{minute.isoformat()}|{fingerprint}'
    variation = int.from_bytes(sha256(seed.encode()).digest()[:4], 'big') % 1000
    daytime = 8 <= minute.hour < 18
    base_watts = (8000 if minute.weekday() >= 5 else 12000) if daytime else 4000
    main_watts = base_watts + variation
    counts = {kind: sum(m.meter_type == kind for m in meters) for kind in ('HVAC', 'LIGHTING')}
    solar_watts = 10000 * max(0, 360 - abs(minute.hour * 60 + minute.minute - 720)) // 360
    plan = []
    for meter in meters:
        if meter.meter_type == 'ELECTRICITY':
            watts = main_watts
        elif meter.meter_type == 'HVAC':
            watts = (main_watts * 30 // 100) // counts['HVAC']
        elif meter.meter_type == 'LIGHTING':
            watts = (main_watts * 15 // 100) // counts['LIGHTING']
        else:  # Inventory is already validated: this is the single SOLAR meter.
            watts = solar_watts
        power = watts / 1000
        plan.append(dict(meter=meter, timestamp=minute, interval_seconds=60,
                         energy_kwh=power / 60, power_kw=power, voltage=230.0))
    return plan


def _building_minute(building_id, minute):
    with transaction.atomic():
        # Building first, then ALL current meters by ascending PK. The building
        # UPDATE lock also blocks normal FK-checked meter creation until commit.
        building = Building.objects.select_for_update().get(pk=building_id)
        meters = list(Meter.objects.select_for_update(no_key=True).filter(
            building=building).order_by('pk'))
        active = [m for m in meters if m.is_active]
        mains = [m for m in active if m.meter_type == 'ELECTRICITY']
        solar = [m for m in active if m.meter_type == 'SOLAR']
        reason = None
        if building.has_solar_installation is None:
            reason = 'unknown_solar_installation'
        elif len(mains) != 1:
            reason = 'requires_exactly_one_active_main'
        elif len(solar) > 1:
            reason = 'multiple_active_solar_meters_unsupported'
        elif building.has_solar_installation is False and any(m.meter_type == 'SOLAR' for m in meters):
            reason = 'no_solar_metadata_conflicts_with_configured_solar_meter'
        elif building.has_solar_installation is True and not solar:
            reason = 'installed_solar_requires_one_active_solar_meter'
        if reason:
            return _result(building_id, 'skipped', reason)

        too_new = [m for m in active if m.created_at > minute]
        skipped_ids = [m.pk for m in too_new]
        if any(m.meter_type in ('ELECTRICITY', 'SOLAR') for m in too_new):
            return _result(building_id, 'skipped', 'required_meter_created_after_interval_start',
                           skipped_meter_ids=skipped_ids)
        eligible = [m for m in active if m.created_at <= minute]
        plan = _plan(building, eligible, minute)

        # Without an inventory manifest we cannot prove how a partial old set
        # was planned. Reject it, and any different membership, without filling it.
        existing_ids = set(EnergyReading.objects.filter(
            meter__building=building, timestamp=minute).values_list('meter_id', flat=True))
        if existing_ids and existing_ids != {m.pk for m in eligible}:
            raise ValidationError('Existing building-minute has a partial or changed meter set; no rows were changed.')
        created = already_existing = 0
        for values in plan:
            _, inserted = ingest_reading(**values)
            created += int(inserted)
            already_existing += int(not inserted)
        return _result(building_id, 'created' if created else 'already_existing',
                       created=created, already_existing=already_existing, skipped_meter_ids=skipped_ids)


def generate_minute(minute, *, now=None):
    """Process one completed UTC minute against the CURRENT database inventory.

    Return {minute, created, already_existing, skipped, failed, buildings}.
    Created/existing count readings; skipped/failed count buildings. Building
    results include reasons and ineligible new submeter IDs. Expected validation
    failures roll back that building only. Unexpected/database errors propagate.
    The caller schedules minutes; this function does not backfill or create assets.
    """
    validate_interval_timestamp(minute)
    if minute > latest_completed_minute(now):
        raise ValidationError('Only completed minutes may be generated.')
    result = dict(minute=minute, created=0, already_existing=0, skipped=0, failed=0, buildings=[])
    # Re-query every cycle; no meter inventory is retained between calls.
    building_ids = list(Building.objects.order_by('pk').values_list('pk', flat=True))
    for building_id in building_ids:
        try:
            outcome = _building_minute(building_id, minute)
        except Building.DoesNotExist:
            outcome = _result(building_id, 'skipped', 'building_removed_during_cycle')
        except ValidationError as error:
            outcome = _result(building_id, 'failed', '; '.join(error.messages))
        result['buildings'].append(outcome)
        result['created'] += outcome['created']
        result['already_existing'] += outcome['already_existing']
        if outcome['status'] in ('skipped', 'failed'):
            result[outcome['status']] += 1
    return result
