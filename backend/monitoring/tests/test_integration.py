from domain.building import Building
from domain.meter import Meter
from domain.energy_reading import EnergyReading

from datetime import datetime, timezone

building = Building(1, "FH Dortmund", "Dortmund", 2500, "University")

meter = Meter(1, "HVAC", "kWh", True)

reading = EnergyReading(
    1, datetime.now(timezone.utc), 1.42, 85.2, "SIMULATED"
)

building.add_meter(meter)
meter.add_reading(reading)

print("Active meters:", len(building.active_meters()))
print("Latest reading:", meter.latest_reading().to_dict())