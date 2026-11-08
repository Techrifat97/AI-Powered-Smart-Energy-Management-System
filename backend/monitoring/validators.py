"""Small field validators shared by S1 models and Django forms."""

from datetime import datetime, timedelta
from math import isfinite

from django.core.exceptions import ValidationError
from django.utils import timezone


def validate_finite(value):
    if not isfinite(value):
        raise ValidationError("Enter a finite number.", code="not_finite")


def validate_positive(value):
    validate_finite(value)
    if value <= 0:
        raise ValidationError("Enter a number greater than zero.", code="not_positive")


def validate_interval_timestamp(value):
    """New telemetry uses UTC minute boundaries; do not silently round timestamps."""
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValidationError("Use a timezone-aware UTC timestamp.", code="not_utc")
    if value.utcoffset() != timedelta(0):
        raise ValidationError("Use a timezone-aware UTC timestamp.", code="not_utc")
    if value.second != 0 or value.microsecond != 0:
        raise ValidationError(
            "Align the timestamp to the start of a UTC minute.", code="not_aligned"
        )
