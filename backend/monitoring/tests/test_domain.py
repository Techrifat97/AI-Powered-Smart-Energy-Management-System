import unittest
from datetime import datetime, timezone
from decimal import Decimal

from backend.monitoring.domain.building import Building
from backend.monitoring.domain.meter import Meter
from backend.monitoring.domain.energy_reading import EnergyReading


class BuildingTests(unittest.TestCase):
    def setUp(self):
        self.building = Building(1, "FH Dortmund", "Dortmund", 2500, "University")

    def test_constructor_and_getters(self):
        self.assertEqual(self.building.id, 1)
        self.assertEqual(self.building.get_name(), "FH Dortmund")
        self.assertEqual(self.building.get_address(), "Dortmund")
        self.assertEqual(self.building.floor_area_m2, 2500.0)
        self.assertIsInstance(self.building.floor_area_m2, float)
        self.assertEqual(self.building.type, "University")
        self.assertIsInstance(self.building.created_at, datetime)
        self.assertEqual(self.building.meters, [])

    def test_name_and_address_setters(self):
        self.building.set_name("Campus North")
        self.building.set_address("Berlin")
        self.assertEqual(self.building.get_name(), "Campus North")
        self.assertEqual(self.building.get_address(), "Berlin")

    def test_building_type_keyword_is_preserved(self):
        building = Building(2, "Lab", "Dortmund", 100, building_type="Research")
        self.assertEqual(building.type, "Research")

    def test_invalid_building_types(self):
        for building_type in ["", "   ", None, 123]:
            with self.subTest(building_type=building_type):
                with self.assertRaises(ValueError):
                    Building(2, "Lab", "Dortmund", 100, building_type)

    def test_invalid_floor_areas(self):
        for area in [0, -1, "invalid", float("nan"), float("inf")]:
            with self.subTest(area=area):
                with self.assertRaises(ValueError):
                    Building(2, "Lab", "Dortmund", area, "University")

    def test_empty_building_has_no_active_meters(self):
        self.assertEqual(self.building.active_meters(), [])

    def test_add_meter_and_filter_active_meters(self):
        active = Meter(1, "HVAC", "kWh")
        inactive = Meter(2, "LIGHTING", "kWh", False)
        self.building.add_meter(active)
        self.building.add_meter(inactive)
        self.assertEqual(self.building.meters, [active, inactive])
        self.assertEqual(self.building.active_meters(), [active])

    def test_invalid_meter_is_not_added(self):
        with self.assertRaises(TypeError):
            self.building.add_meter("meter")
        self.assertEqual(self.building.meters, [])

    def test_buildings_have_separate_meter_lists(self):
        other = Building(2, "Lab", "Dortmund", 100, "Research")
        self.building.add_meter(Meter(1, "HVAC", "kWh"))
        self.assertEqual(other.meters, [])


class MeterTests(unittest.TestCase):
    def setUp(self):
        self.meter = Meter(1, "HVAC", "kWh")
        self.timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_constructor_and_getters(self):
        self.assertEqual(self.meter.get_id(), 1)
        self.assertEqual(self.meter.get_category(), "HVAC")
        self.assertEqual(self.meter.get_unit(), "kWh")
        self.assertTrue(self.meter.get_status())
        self.assertEqual(self.meter.readings, [])

    def test_setters(self):
        self.meter.set_category("LIGHTING")
        self.meter.set_unit("Wh")
        self.meter.set_status(False)
        self.assertEqual(self.meter.get_category(), "LIGHTING")
        self.assertEqual(self.meter.get_unit(), "Wh")
        self.assertFalse(self.meter.get_status())

    def test_allowed_categories(self):
        for category in ["HVAC", "LIGHTING", "PLUG", "SOLAR"]:
            with self.subTest(category=category):
                meter = Meter(2, category, "kWh")
                self.meter.set_category(category)
                self.assertEqual(meter.get_category(), category)
                self.assertEqual(self.meter.get_category(), category)

    def test_invalid_category_in_constructor(self):
        with self.assertRaises(ValueError):
            Meter(2, "WATER", "kWh")

    def test_invalid_category_setter_preserves_value(self):
        with self.assertRaises(ValueError):
            self.meter.set_category("WATER")
        self.assertEqual(self.meter.get_category(), "HVAC")

    def test_inactive_constructor(self):
        meter = Meter(2, "PLUG", "kWh", False)
        self.assertFalse(meter.get_status())

    def test_invalid_status_in_constructor(self):
        for status in ["False", 0, 1, None]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    Meter(2, "PLUG", "kWh", status)

    def test_invalid_status_setter_preserves_value(self):
        for status in ["False", 0, 1, None]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    self.meter.set_status(status)
                self.assertTrue(self.meter.get_status())

    def test_latest_reading_without_readings(self):
        self.assertIsNone(self.meter.latest_reading())

    def test_add_reading(self):
        reading = EnergyReading(1, self.timestamp, 1, 2, "MANUAL")
        self.meter.add_reading(reading)
        self.assertEqual(self.meter.readings, [reading])
        self.assertIs(self.meter.latest_reading(), reading)

    def test_latest_reading_uses_timestamp_not_insertion_order(self):
        later = datetime(2026, 1, 3, tzinfo=timezone.utc)
        middle = datetime(2026, 1, 2, tzinfo=timezone.utc)
        newest = EnergyReading(1, later, 2, 3, "MANUAL")
        older = EnergyReading(2, self.timestamp, 1, 2, "SIMULATED")
        first = EnergyReading(3, middle, 1, 2, "MANUAL")
        self.meter.add_reading(first)
        self.meter.add_reading(newest)
        self.meter.add_reading(older)
        self.assertIs(self.meter.latest_reading(), newest)
        self.assertEqual(self.meter.readings, [first, newest, older])

    def test_equal_timestamps_keep_first_reading(self):
        first = EnergyReading(1, self.timestamp, 1, 2, "MANUAL")
        second = EnergyReading(2, self.timestamp, 2, 3, "MANUAL")
        self.meter.add_reading(first)
        self.meter.add_reading(second)
        self.assertIs(self.meter.latest_reading(), first)

    def test_invalid_reading_is_not_added(self):
        with self.assertRaises(TypeError):
            self.meter.add_reading({"consumption_kwh": 1})
        self.assertEqual(self.meter.readings, [])

    def test_meters_have_separate_reading_lists(self):
        other = Meter(2, "SOLAR", "kWh")
        self.meter.add_reading(EnergyReading(1, self.timestamp, 1, 2, "MANUAL"))
        self.assertEqual(other.readings, [])


class EnergyReadingTests(unittest.TestCase):
    def setUp(self):
        self.timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.reading = EnergyReading(1, self.timestamp, "1.42", 85.2, "SIMULATED")

    def test_constructor_and_getters(self):
        self.assertEqual(self.reading.id, 1)
        self.assertEqual(self.reading.get_timestamp(), self.timestamp)
        self.assertEqual(self.reading.get_consumption(), Decimal("1.42"))
        self.assertIsInstance(self.reading.get_consumption(), Decimal)
        self.assertEqual(self.reading.get_power(), 85.2)
        self.assertIsInstance(self.reading.get_power(), float)
        self.assertEqual(self.reading.get_source(), "SIMULATED")
        self.assertTrue(self.reading.is_valid)

    def test_setters(self):
        self.reading.set_consumption("2.75")
        self.reading.set_power("3.5")
        self.reading.set_source("MANUAL")
        self.assertEqual(self.reading.get_consumption(), Decimal("2.75"))
        self.assertEqual(self.reading.get_power(), 3.5)
        self.assertEqual(self.reading.get_source(), "MANUAL")

    def test_zero_values_are_allowed(self):
        reading = EnergyReading(2, self.timestamp, 0, 0, "MANUAL")
        self.assertEqual(reading.get_consumption(), Decimal("0"))
        self.assertEqual(reading.get_power(), 0.0)
        self.reading.set_consumption(0)
        self.reading.set_power(0)
        self.assertEqual(self.reading.get_consumption(), Decimal("0"))
        self.assertEqual(self.reading.get_power(), 0.0)

    def test_invalid_consumption_in_constructor(self):
        for consumption in [-1, "invalid", "NaN", "Infinity"]:
            with self.subTest(consumption=consumption):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, consumption, 2, "MANUAL")

    def test_invalid_consumption_setter_preserves_value(self):
        for consumption in [-1, "invalid", "NaN", "Infinity"]:
            with self.subTest(consumption=consumption):
                with self.assertRaises(ValueError):
                    self.reading.set_consumption(consumption)
                self.assertEqual(self.reading.get_consumption(), Decimal("1.42"))

    def test_invalid_power_in_constructor(self):
        for power in ["invalid", float("nan"), float("inf")]:
            with self.subTest(power=power):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, 1, power, "MANUAL")

    def test_invalid_power_setter_preserves_value(self):
        for power in ["invalid", float("nan"), float("inf")]:
            with self.subTest(power=power):
                with self.assertRaises(ValueError):
                    self.reading.set_power(power)
                self.assertEqual(self.reading.get_power(), 85.2)

    def test_invalid_source_in_constructor(self):
        with self.assertRaises(ValueError):
            EnergyReading(2, self.timestamp, 1, 2, "UNKNOWN")

    def test_invalid_source_setter_preserves_value(self):
        with self.assertRaises(ValueError):
            self.reading.set_source("UNKNOWN")
        self.assertEqual(self.reading.get_source(), "SIMULATED")

    def test_invalid_timestamps(self):
        for timestamp in ["2026-01-01", None, 123]:
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(TypeError):
                    EnergyReading(2, timestamp, 1, 2, "MANUAL")

    def test_false_validity_flag(self):
        reading = EnergyReading(2, self.timestamp, 1, 2, "MANUAL", False)
        self.assertFalse(reading.is_valid)
        self.assertFalse(reading.to_dict()["is_valid"])

    def test_invalid_validity_flags(self):
        for is_valid in ["False", 0, 1, None]:
            with self.subTest(is_valid=is_valid):
                with self.assertRaises(ValueError):
                    EnergyReading(2, self.timestamp, 1, 2, "MANUAL", is_valid)

    def test_to_dict(self):
        self.assertEqual(self.reading.to_dict(), {
            "id": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "consumption_kwh": "1.42",
            "power_kw": 85.2,
            "source": "SIMULATED",
            "is_valid": True
        })


if __name__ == "__main__":
    unittest.main()
