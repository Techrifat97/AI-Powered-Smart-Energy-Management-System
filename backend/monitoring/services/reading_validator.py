"""Validate readings without changing their values or storing them."""

from decimal import Decimal
from math import isfinite

from ..domain.energy_reading import EnergyReading
from ..domain.meter import Meter
from ..domain.validation import validate_utc_timestamp


class ReadingValidator:
    """Apply the stricter ingestion rules to existing domain objects."""

    def validate(self, meter: Meter, reading: EnergyReading) -> None:
        """Raise TypeError or ValueError when a reading cannot be accepted."""
        if not isinstance(meter, Meter):
            raise TypeError("Expected a Meter object")
        if not isinstance(reading, EnergyReading):
            raise TypeError("Expected an EnergyReading object")
        if not isinstance(meter.is_active, bool):
            raise TypeError("Meter activity must be a Boolean")
        if not meter.is_active:
            raise ValueError("Cannot accept readings from an inactive meter")
        if not isinstance(reading.is_valid, bool):
            raise TypeError("Reading validity must be a Boolean")
        if not reading.is_valid:
            raise ValueError("Reading is marked invalid")

        consumption = reading.consumption_kwh
        if not isinstance(consumption, Decimal):
            raise TypeError("Consumption must be a Decimal")
        if not consumption.is_finite() or consumption < 0:
            raise ValueError("Consumption must be finite and nonnegative")

        power = reading.power_kw
        if isinstance(power, bool) or not isinstance(power, (int, float)):
            raise TypeError("Power must be a number")
        if not isfinite(power):
            raise ValueError("Power must be finite")
        validate_utc_timestamp(reading.timestamp)
