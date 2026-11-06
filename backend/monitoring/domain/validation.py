"""Small validation helpers shared by the S1 domain and services."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


def validate_utc_timestamp(value, name="Timestamp"):
    """Require a datetime with a timezone and a zero UTC offset."""
    if not isinstance(value, datetime):
        raise TypeError(name + " must be a datetime object")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(name + " must be timezone-aware UTC")


def to_decimal(value, name, allow_negative=False):
    """Convert a finite energy value without calculating with floats."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise TypeError(name + " must be a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(name + " must be a number") from None
    if not result.is_finite():
        raise ValueError(name + " must be finite")
    if not allow_negative and result < 0:
        raise ValueError(name + " cannot be negative")
    return result
