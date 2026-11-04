from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite
import random
import time


class MeterReadingStream:
    def __init__(self, events):
        self.events = iter(events)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.events)


class TelemetryGenerator:
    """Generate measurements lazily; the waiting interval does not set their duration."""

    def __init__(self, meters, measurement_seconds=60):
        if isinstance(measurement_seconds, bool) or not isinstance(measurement_seconds, (int, float)):
            raise TypeError("Measurement duration must be a number")
        if not isfinite(measurement_seconds) or measurement_seconds <= 0:
            raise ValueError("Measurement duration must be finite and positive")
        self.measurement_seconds = float(measurement_seconds)
        # Keep the meters so an iterator can be reused in every cycle.
        self.meters = list(meters)

        for meter in self.meters:
            if not isinstance(meter, dict):
                raise TypeError("Each meter must be a dictionary")
            for field in ["meter_id", "category", "is_active"]:
                if field not in meter:
                    raise ValueError("Missing meter field: " + field)

            if isinstance(meter["meter_id"], bool) or not isinstance(meter["meter_id"], int):
                raise TypeError("Meter ID must be an integer")
            if meter["meter_id"] <= 0:
                raise ValueError("Meter ID must be positive")
            if not isinstance(meter["category"], str):
                raise TypeError("Meter category must be a string")
            if not meter["category"].strip():
                raise ValueError("Meter category cannot be empty")
            if not isinstance(meter["is_active"], bool):
                raise TypeError("Meter activity must be True or False")
            if meter["category"] == "BATTERY" and "battery_mode" in meter:
                if meter["battery_mode"] not in ["CHARGING", "DISCHARGING"]:
                    raise ValueError("Battery mode must be CHARGING or DISCHARGING")

    def generate(self, cycles=1, interval=0):
        if isinstance(cycles, bool) or not isinstance(cycles, int):
            raise TypeError("Cycles must be an integer")
        if cycles < 0:
            raise ValueError("Cycles cannot be negative")
        if isinstance(interval, bool) or not isinstance(interval, (int, float)):
            raise TypeError("Interval must be a number")
        if not isfinite(interval) or interval < 0:
            raise ValueError("Interval must be finite and nonnegative")

        if not self.meters:
            return

        for cycle in range(cycles):
            for meter in self.meters:
                power_kw = round(random.uniform(0, 5), 2)
                # Calculate energy from the same power measurement, not another random value.
                energy_kwh = (
                    Decimal(str(power_kw)) * Decimal(str(self.measurement_seconds))
                    / Decimal("3600")
                )
                reading = {
                    "meter_id": meter["meter_id"],
                    "category": meter["category"],
                    "is_active": meter["is_active"],
                    "power_kw": power_kw,
                    "consumption_kwh": float(energy_kwh),
                    "measurement_seconds": self.measurement_seconds,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                if meter["category"] == "BATTERY":
                    mode = meter.get("battery_mode")
                    if mode is None:
                        mode = random.choice(["CHARGING", "DISCHARGING"])
                    reading["battery_mode"] = mode

                yield reading

            if cycle < cycles - 1 and interval > 0:
                time.sleep(interval)


if __name__ == "__main__":
    meters = [
        {"meter_id": 1, "category": "HVAC", "is_active": True},
        {"meter_id": 2, "category": "SOLAR", "is_active": True},
        {"meter_id": 3, "category": "BATTERY", "is_active": False},
        {"meter_id": 4, "category": "HVAC", "is_active": True},
        {"meter_id": 5, "category": "SOLAR", "is_active": True},
        {"meter_id": 6, "category": "BATTERY", "is_active": True},
        {"meter_id": 7, "category": "HVAC", "is_active": False},
        {"meter_id": 8, "category": "SOLAR", "is_active": True},
        {"meter_id": 9, "category": "BATTERY", "is_active": True},
        {"meter_id": 10, "category": "HVAC", "is_active": True}
    ]

    generator = TelemetryGenerator(meters)
    readings = generator.generate(cycles=5, interval=1)

    stream = MeterReadingStream(readings)

    for reading in stream:
        print(reading)
