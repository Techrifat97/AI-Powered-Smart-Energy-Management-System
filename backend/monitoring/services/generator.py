"""Deterministic SYNTHETIC telemetry; these are not physical measurements."""

from datetime import datetime, timedelta

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
    """Stream the original v1 measurements through composed profile strategies."""
    from monitoring.services.profiles import TelemetryGenerator
    return TelemetryGenerator().iter_readings(building, meters, minute)


def _building_minute(building_id, minute, *, outbox=False):
    with transaction.atomic():
        # Building first, then all current meters by ascending PK. The building
        # UPDATE lock also blocks normal FK-checked meter creation until commit.
        building = Building.objects.select_for_update().get(pk=building_id)
        if outbox:
            from monitoring.models import TelemetryBatch
            frozen = TelemetryBatch.objects.filter(building=building, timestamp=minute).first()
            if frozen:
                return _result(building_id, 'already_existing', 'durable_batch_already_staged')
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

        # Without a historical inventory manifest, partial/different meter sets
        # cannot be safely completed and are rejected without modification.
        existing_ids = set(EnergyReading.objects.filter(
            meter__building=building, timestamp=minute).values_list('meter_id', flat=True))
        if existing_ids and existing_ids != {m.pk for m in eligible}:
            raise ValidationError('Existing building-minute has a partial or changed meter set; no rows were changed.')
        if outbox:
            from monitoring.services.kafka_pipeline import stage_batch
            batch, inserted = stage_batch(building, minute, plan)
            return _result(building_id, 'created' if inserted else 'already_existing',
                           'durable_batch_staged', created=len(batch.payload['readings']) if inserted else 0)
        created = already_existing = 0
        for values in plan:
            _, inserted = ingest_reading(**values)
            created += int(inserted)
            already_existing += int(not inserted)
        return _result(building_id, 'created' if created else 'already_existing',
                       created=created, already_existing=already_existing, skipped_meter_ids=skipped_ids)


def generate_minute(minute, *, now=None, outbox=False):
    """Process one completed UTC minute against the current database inventory.

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
            outcome = _building_minute(building_id, minute, outbox=outbox)
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
