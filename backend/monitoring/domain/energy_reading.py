
from datetime import datetime, timezone
from decimal import Decimal


class EnergyReading:
    def __init__(self, reading_id, timestamp, consumption_kwh,
                 power_kw, source, is_valid=True):

        self.id = reading_id
        self.timestamp = timestamp
        self.consumption_kwh = Decimal(str(consumption_kwh))
        self.power_kw = float(power_kw)
        self.source = source
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
        if Decimal(str(new_consumption)) < 0:
            raise ValueError("Consumption cannot be negative")
        self.consumption_kwh = Decimal(str(new_consumption))

    def set_power(self, new_power):
        self.power_kw = float(new_power)

    def set_source(self, new_source):
        if new_source not in ("SIMULATED", "MANUAL"):
            raise ValueError("Invalid reading source")
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


if __name__ == "__main__":
    reading1 = EnergyReading(
        1,
        datetime.now(timezone.utc),
        1.42,
        85.2,
        "SIMULATED"
    )

    print(reading1.to_dict())
