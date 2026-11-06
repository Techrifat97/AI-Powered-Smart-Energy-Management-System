import unittest
from datetime import datetime, timezone

from backend.monitoring.domain.building import Building
from backend.monitoring.domain.meter import Meter
from backend.monitoring.domain.energy_reading import EnergyReading


class MonitoringIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.building = Building(1, "FH Dortmund", "Dortmund", 2500, "University")
        self.active_meter = Meter(1, "HVAC", "kWh")
        self.inactive_meter = Meter(2, "LIGHTING", "kWh", False)
        self.building.add_meter(self.active_meter)
        self.building.add_meter(self.inactive_meter)

    def test_building_meter_reading_flow(self):
        timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        reading = EnergyReading(1, timestamp, "1.42", 85.2, "SIMULATED")
        self.active_meter.add_reading(reading)

        self.assertEqual(self.building.active_meters(), [self.active_meter])
        self.assertIs(self.active_meter.latest_reading(), reading)
        self.assertEqual(self.active_meter.latest_reading().to_dict(), {
            "id": 1,
            "timestamp": "2026-01-01T12:00:00+00:00",
            "consumption_kwh": "1.42",
            "power_kw": 85.2,
            "source": "SIMULATED",
            "is_valid": True
        })

    def test_status_changes_update_active_meters(self):
        self.active_meter.set_status(False)
        self.assertEqual(self.building.active_meters(), [])

        self.inactive_meter.set_status(True)
        self.assertEqual(self.building.active_meters(), [self.inactive_meter])

    def test_inactive_meter_keeps_its_readings(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reading = EnergyReading(1, timestamp, 2, 3, "MANUAL")
        self.active_meter.add_reading(reading)
        self.active_meter.set_status(False)

        self.assertEqual(self.building.active_meters(), [])
        self.assertIs(self.active_meter.latest_reading(), reading)


if __name__ == "__main__":
    unittest.main()
