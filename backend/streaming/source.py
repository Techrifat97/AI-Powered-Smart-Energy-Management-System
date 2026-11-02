from datetime import datetime, timezone
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
    def __init__(self, meters):
        self.meters = meters

    def generate(self, cycles=1, interval=0):
        for cycle in range(cycles):
            for meter in self.meters:
                reading = {
                    "meter_id": meter["meter_id"],
                    "category": meter["category"],
                    "is_active": meter["is_active"],
                    "power_kw": round(random.uniform(0, 5), 2),
                    "consumption_kwh": round(random.uniform(0, 2), 2),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                yield reading

            if cycle < cycles - 1:
                time.sleep(interval)



if __name__ == "__main__":
    meters = [
        {"meter_id": 1, "category": "HVAC", "is_active": True},
        {"meter_id": 2, "category": "SOLAR", "is_active": True},
        {"meter_id": 3, "category": "BATTERY", "is_active": False}
    ]

    generator = TelemetryGenerator(meters)

    readings = generator.generate(cycles=2, interval=1)

    stream = MeterReadingStream(readings)

    for reading in stream:
        print(reading)

