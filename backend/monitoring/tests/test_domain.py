import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.monitoring.domain.building import Building
from backend.monitoring.domain.energy_reading import EnergyReading
from backend.monitoring.domain.meter import Meter


class BuildingTests(unittest.TestCase):
    def test_building_attributes_and_setters(self):
        building = Building(1, "FH Dortmund", "Dortmund", 2500, "University")
        self.assertEqual(building.id, 1)
        self.assertEqual(building.get_name(), "FH Dortmund")
        self.assertEqual(building.get_address(), "Dortmund")
        self.assertEqual(building.floor_area_m2, 2500.0)
        self.assertIsInstance(building.floor_area_m2, float)
        self.assertEqual(building.type, "University")
        self.assertIsInstance(building.created_at, datetime)
        self.assertEqual(building.meters, [])

        building.set_name("Campus North")
        building.set_address("Berlin")
        self.assertEqual(building.get_name(), "Campus North")
        self.assertEqual(building.get_address(), "Berlin")
        other = Building(2, "Lab", "Dortmund", 100, building_type="Research")
        self.assertEqual(other.type, "Research")

        for building_type in ["", "   ", None, 123]:
            with self.subTest(building_type=building_type):
                with self.assertRaises(ValueError):
                    Building(2, "Lab", "Dortmund", 100, building_type)
        for area in [0, -1, "invalid", float("nan"), float("inf")]:
            with self.subTest(area=area):
                with self.assertRaises(ValueError):
                    Building(2, "Lab", "Dortmund", area, "Research")

    def test_building_meters_and_active_status(self):
        building = Building(1, "Campus", "Dortmund", 2500, "University")
        other = Building(2, "Lab", "Dortmund", 100, "Research")
        self.assertEqual(building.active_meters(), [])
        with self.assertRaises(TypeError):
            building.add_meter("meter")
        self.assertEqual(building.meters, [])

        active = Meter(1, "HVAC", "kWh")
        inactive = Meter(2, "LIGHTING", "kWh", False)
        building.add_meter(active)
        building.add_meter(inactive)
        self.assertEqual(building.meters, [active, inactive])
        self.assertEqual(building.active_meters(), [active])
        self.assertEqual(other.meters, [])

        timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        reading = EnergyReading(1, timestamp, "1.42", 85.2, "SIMULATED")
        active.add_reading(reading)
        self.assertIs(active.latest_reading(), reading)
        self.assertEqual(active.latest_reading().to_dict(), {
            "id": 1, "timestamp": timestamp.isoformat(),
            "consumption_kwh": "1.42", "power_kw": 85.2,
            "source": "SIMULATED", "is_valid": True
        })
        active.set_status(False)
        self.assertEqual(building.active_meters(), [])
        self.assertIs(active.latest_reading(), reading)
        inactive.set_status(True)
        self.assertEqual(building.active_meters(), [inactive])


class MeterTests(unittest.TestCase):
    def test_meter_attributes_and_validation(self):
        meter = Meter(1, "HVAC", "kWh")
        self.assertEqual(meter.get_id(), 1)
        self.assertEqual(meter.get_category(), "HVAC")
        self.assertEqual(meter.get_unit(), "kWh")
        self.assertTrue(meter.get_status())
        self.assertEqual(meter.readings, [])
        for category in ["HVAC", "LIGHTING", "PLUG", "SOLAR"]:
            with self.subTest(category=category):
                other = Meter(2, category, "kWh")
                meter.set_category(category)
                self.assertEqual(other.get_category(), category)
                self.assertEqual(meter.get_category(), category)
        meter.set_category("LIGHTING")
        meter.set_unit("Wh")
        meter.set_status(False)
        self.assertEqual(meter.get_category(), "LIGHTING")
        self.assertEqual(meter.get_unit(), "Wh")
        self.assertFalse(meter.get_status())
        self.assertFalse(Meter(2, "PLUG", "kWh", False).get_status())

        with self.assertRaises(ValueError):
            Meter(2, "WATER", "kWh")
        with self.assertRaises(ValueError):
            meter.set_category("WATER")
        self.assertEqual(meter.get_category(), "LIGHTING")
        meter.set_status(True)
        for status in ["False", 0, 1, None]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    Meter(2, "PLUG", "kWh", status)
                with self.assertRaises(ValueError):
                    meter.set_status(status)
                self.assertTrue(meter.get_status())

    def test_meter_readings_and_latest_reading(self):
        meter = Meter(1, "HVAC", "kWh")
        other = Meter(2, "SOLAR", "kWh")
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertIsNone(meter.latest_reading())
        with self.assertRaises(TypeError):
            meter.add_reading({"consumption_kwh": 1})
        self.assertEqual(meter.readings, [])

        first = EnergyReading(1, timestamp, 1, 2, "MANUAL")
        equal_time = EnergyReading(2, timestamp, 2, 3, "MANUAL")
        meter.add_reading(first)
        self.assertEqual(meter.readings, [first])
        self.assertIs(meter.latest_reading(), first)
        meter.add_reading(equal_time)
        self.assertIs(meter.latest_reading(), first)
        newest = EnergyReading(3, timestamp + timedelta(days=2), 2, 3, "MANUAL")
        middle = EnergyReading(4, timestamp + timedelta(days=1), 1, 2, "SIMULATED")
        meter.add_reading(newest)
        meter.add_reading(middle)
        self.assertIs(meter.latest_reading(), newest)
        self.assertEqual(meter.readings, [first, equal_time, newest, middle])
        self.assertEqual(other.readings, [])


class EnergyReadingTests(unittest.TestCase):
    def setUp(self):
        self.timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.reading = EnergyReading(1, self.timestamp, "1.42", 85.2, "SIMULATED")

    def test_reading_attributes_setters_and_serialization(self):
        self.assertEqual(self.reading.id, 1)
        self.assertEqual(self.reading.get_timestamp(), self.timestamp)
        self.assertEqual(self.reading.get_consumption(), Decimal("1.42"))
        self.assertIsInstance(self.reading.get_consumption(), Decimal)
        self.assertEqual(self.reading.get_power(), 85.2)
        self.assertIsInstance(self.reading.get_power(), float)
        self.assertEqual(self.reading.get_source(), "SIMULATED")
        self.assertTrue(self.reading.is_valid)
        self.assertEqual(self.reading.to_dict(), {
            "id": 1, "timestamp": self.timestamp.isoformat(),
            "consumption_kwh": "1.42", "power_kw": 85.2,
            "source": "SIMULATED", "is_valid": True
        })
        self.reading.set_consumption("2.75")
        self.reading.set_power("3.5")
        self.reading.set_source("MANUAL")
        self.assertEqual(self.reading.get_consumption(), Decimal("2.75"))
        self.assertEqual(self.reading.get_power(), 3.5)
        self.assertEqual(self.reading.get_source(), "MANUAL")
        zero = EnergyReading(2, self.timestamp, 0, 0, "MANUAL")
        self.reading.set_consumption(0)
        self.reading.set_power(0)
        for reading in [zero, self.reading]:
            with self.subTest(reading_id=reading.id):
                self.assertEqual(reading.get_consumption(), Decimal("0"))
                self.assertEqual(reading.get_power(), 0.0)
        invalid = EnergyReading(3, self.timestamp, 1, 2, "MANUAL", False)
        self.assertFalse(invalid.is_valid)
        self.assertFalse(invalid.to_dict()["is_valid"])

    def test_reading_rejects_invalid_values(self):
        for consumption in [-1, "invalid", "NaN", "Infinity"]:
            with self.subTest(consumption=consumption):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, consumption, 2, "MANUAL")
                with self.assertRaises(ValueError):
                    self.reading.set_consumption(consumption)
                self.assertEqual(self.reading.get_consumption(), Decimal("1.42"))
        for power in ["invalid", float("nan"), float("inf")]:
            with self.subTest(power=power):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, 1, power, "MANUAL")
                with self.assertRaises(ValueError):
                    self.reading.set_power(power)
                self.assertEqual(self.reading.get_power(), 85.2)
        with self.assertRaises(ValueError):
            EnergyReading(2, self.timestamp, 1, 2, "UNKNOWN")
        with self.assertRaises(ValueError):
            self.reading.set_source("UNKNOWN")
        self.assertEqual(self.reading.get_source(), "SIMULATED")
        for timestamp in ["2026-01-01", None, 123]:
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(TypeError):
                    EnergyReading(2, timestamp, 1, 2, "MANUAL")
        for is_valid in ["False", 0, 1, None]:
            with self.subTest(is_valid=is_valid):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, 1, 2, "MANUAL", is_valid)


if __name__ == "__main__":
    unittest.main()
