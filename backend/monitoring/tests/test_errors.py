import unittest
from datetime import datetime, timezone

from backend.monitoring.domain.building import Building
from backend.monitoring.domain.energy_reading import EnergyReading
from backend.monitoring.domain.meter import Meter
from backend.monitoring.errors import (
    InvalidBuildingError,
    InvalidMeterError,
    MonitoringError,
    MonitoringErrorHandler,
    MonitoringTypeError,
)


class MonitoringExceptionTests(unittest.TestCase):
    def test_hierarchy_keeps_builtin_compatibility(self):
        self.assertTrue(issubclass(InvalidMeterError, MonitoringError))
        self.assertTrue(issubclass(InvalidMeterError, ValueError))
        self.assertTrue(issubclass(MonitoringTypeError, TypeError))

    def test_building_with_empty_type_raises_invalid_building(self):
        with self.assertRaises(InvalidBuildingError) as ctx:
            Building(1, "HQ", "Main St", 100, "  ")
        self.assertEqual(ctx.exception.code, "INVALID_BUILDING")

    def test_meter_with_unknown_category_raises_invalid_meter(self):
        with self.assertRaises(InvalidMeterError):
            Meter(1, "BOGUS", "kWh")

    def test_reading_with_non_datetime_timestamp_raises_type_error(self):
        with self.assertRaises(MonitoringTypeError):
            EnergyReading(1, "2026-01-01", 1, 1, "meter")


class MonitoringErrorHandlerTests(unittest.TestCase):
    def setUp(self):
        self.handler = MonitoringErrorHandler()

    def test_safe_call_returns_value_on_success(self):
        result = self.handler.safe_call(Meter, 1, "HVAC", "kWh")
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["value"], Meter)

    def test_safe_call_turns_domain_error_into_result(self):
        result = self.handler.safe_call(Meter, 1, "BOGUS", "kWh")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "INVALID_METER")

    def test_safe_call_labels_unexpected_errors(self):
        result = self.handler.safe_call(lambda: 1 / 0)
        self.assertEqual(result["code"], "UNEXPECTED_ERROR")


if __name__ == "__main__":
    unittest.main()
