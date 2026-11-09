"""Validate and store one new 60-second telemetry reading."""

from datetime import datetime, timedelta
from sys import float_info

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import DateTimeField, ExpressionWrapper, F

from monitoring.models import EnergyReading, Meter
from monitoring.validators import validate_interval_timestamp


MEASUREMENT_FIELDS = ('interval_seconds', 'energy_kwh', 'power_kw', 'voltage')


def _retry_result(existing, candidate):
    if all(getattr(existing, field) == getattr(candidate, field) for field in MEASUREMENT_FIELDS):
        return existing, False
    raise ValidationError({
        'timestamp': ValidationError(
            'This meter already has different measurements or duration at this timestamp.',
            code='conflicting_reading',
        ),
    })


def ingest_reading(
    meter: Meter | int, *, timestamp: datetime, interval_seconds: int,
    energy_kwh: int | float, power_kw: int | float, voltage: int | float,
) -> tuple[EnergyReading, bool]:
    """Return (saved_reading, created): True for insertion, False for exact retry.

    Pass a saved Meter or its integer primary key (not device_id), an aware UTC
    minute start, integer duration 60, and Python int/float measurements. Strings,
    booleans and implicit timestamp/duration conversions are rejected. Model
    validators enforce finite, nonnegative measurements; kWh need not equal kW/60.

    Invalid input, missing/inactive meters, conflicts, same-meter overlap and
    unresolved earlier coverage raise Django ValidationError. An unknown-duration
    interval starting before the new end blocks insertion, however old it is.
    An unknown interval starting at/after the new end cannot overlap this reading.
    Exact retries add no coverage and return before overlap checks; meters must
    still be active. Comparisons use exact stored float values, not a tolerance.

    A transaction and meter-row lock serialize service calls for that meter and
    coordinate normal meter updates/deactivation. Uniqueness also protects the
    key at the database. Writers bypassing this service do not gain its coverage
    validation; this is not a database-wide prohibition on overlapping intervals.
    """
    if isinstance(meter, Meter):
        meter_id = meter.pk
    else:
        meter_id = meter
    if type(meter_id) is not int or meter_id <= 0:
        raise ValidationError({'meter': 'Pass an existing Meter or its integer primary key.'})

    # Guard before full_clean(): Django fields normally coerce strings/dates.
    try:
        validate_interval_timestamp(timestamp)
    except ValidationError as error:
        raise ValidationError({'timestamp': error}) from None
    if type(interval_seconds) is not int or interval_seconds != 60:
        raise ValidationError({'interval_seconds': 'New telemetry requires integer duration 60.'})
    try:
        new_end = timestamp + timedelta(seconds=60)
    except OverflowError:
        raise ValidationError({'timestamp': 'The interval end is outside the supported datetime range.'}) from None
    measurements = dict(energy_kwh=energy_kwh, power_kw=power_kw, voltage=voltage)
    for field, value in measurements.items():
        if type(value) not in (int, float):
            raise ValidationError({field: 'Supply a Python int or float, not a converted value.'})
        if isinstance(value, int) and abs(value) > float_info.max:
            raise ValidationError({field: 'The measurement cannot be represented as a finite float.'})

    with transaction.atomic():
        try:
            # NO KEY UPDATE serializes service calls while allowing FK checks
            # by other writers. Such writers still cannot bypass DB uniqueness.
            locked_meter = Meter.objects.select_for_update(no_key=True).get(pk=meter_id)
        except Meter.DoesNotExist:
            raise ValidationError({'meter': 'The meter does not exist.'}) from None
        if not locked_meter.is_active:
            raise ValidationError({'meter': 'The meter is inactive.'})

        reading = EnergyReading(
            meter=locked_meter, timestamp=timestamp, interval_seconds=interval_seconds,
            **measurements,
        )
        # full_clean() normally reports the UniqueConstraint as invalid before
        # we can recognize a retry. Keep field/model validation, then handle the
        # key explicitly; ALL database constraints still apply to the INSERT.
        reading.full_clean(validate_constraints=False)
        same_meter = EnergyReading.objects.filter(meter=locked_meter)
        existing = same_meter.filter(timestamp=timestamp).first()
        if existing is not None:
            return _retry_result(existing, reading)

        earlier = same_meter.filter(timestamp__lt=new_end)
        if earlier.filter(interval_seconds__isnull=True).exists():
            raise ValidationError({
                'timestamp': ValidationError(
                    'An earlier reading has unknown duration; verify its coverage before ingestion.',
                    code='unknown_coverage',
                ),
            })
        interval_end = ExpressionWrapper(
            F('timestamp') + F('interval_seconds') * timedelta(seconds=1),
            output_field=DateTimeField(),
        )
        if earlier.annotate(interval_end=interval_end).filter(interval_end__gt=timestamp).exists():
            raise ValidationError({
                'timestamp': ValidationError(
                    'This interval overlaps an existing reading for the same meter.',
                    code='overlapping_reading',
                ),
            })

        try:
            # Roll back this savepoint before querying after a unique-key race.
            with transaction.atomic():
                reading.save(force_insert=True)
        except IntegrityError as error:
            constraint = getattr(getattr(error.__cause__, 'diag', None), 'constraint_name', None)
            if constraint != 's1_reading_meter_timestamp_unique':
                raise
            return _retry_result(same_meter.get(timestamp=timestamp), reading)
        return reading, True
