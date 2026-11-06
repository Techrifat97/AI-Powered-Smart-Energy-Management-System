from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from ..errors import InvalidReadingError, MonitoringTypeError


class EnergyReading:
    def __init__(self, reading_id, timestamp, consumption_kwh,
                 power_kw, source, is_valid=True):
        if not isinstance(timestamp, datetime):
            raise MonitoringTypeError("Timestamp must be a datetime object")
        if not isinstance(is_valid, bool):
            raise InvalidReadingError("Reading validity must be True or False")

        self.id = reading_id
        self.timestamp = timestamp
        self.set_consumption(consumption_kwh)
        self.set_power(power_kw)
        self.set_source(source)
        self.is_valid = is_valid

    def get_timestamp(self):
        return self.timestamp

    def get_consumption(self):
        return self.consumption_kwh

    def get_power(self):
        return self.power_kw

    def get_source(self):
        return self.source

    def set_consumption(self, new_consumption):
        try:
            consumption = Decimal(str(new_consumption))
        except InvalidOperation:
            raise InvalidReadingError("Consumption must be a number")
        if not consumption.is_finite() or consumption < 0:
            raise InvalidReadingError("Consumption must be finite and nonnegative")
        self.consumption_kwh = consumption

    def set_power(self, new_power):
        power = float(new_power)
        if not isfinite(power):
            raise InvalidReadingError("Power must be finite")
        self.power_kw = power

    def set_source(self, new_source):
        if new_source not in ("SIMULATED", "MANUAL"):
            raise InvalidReadingError("Invalid reading source")
        self.source = new_source

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "consumption_kwh": str(self.consumption_kwh),
            "power_kw": self.power_kw,
            "source": self.source,
            "is_valid": self.is_valid
        }
