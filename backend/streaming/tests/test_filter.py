import unittest

from backend.streaming.filter import MeterFilter
from backend.streaming.processor import StreamProcessor
from backend.streaming.source import MeterReadingStream, TelemetryGenerator


class TestMeterFilter(unittest.TestCase):

    def setUp(self):
        self.default_filter = MeterFilter(min_power_kw=1.0, filter_inactive=True)

    def test_inheritance(self):
        """Verify MeterFilter inherits from StreamProcessor."""
        self.assertIsInstance(self.default_filter, StreamProcessor)

    def test_active_meter_above_threshold_passes(self):
        """Active reading above min_power_kw should pass through."""
        event = {
            "meter_id": 1,
            "category": "HVAC",
            "is_active": True,
            "power_kw": 2.5,
            "consumption_kwh": 1.2,
            "timestamp": "2026-11-03T12:00:00+00:00",
        }
        result = self.default_filter.process(event)
        self.assertIsNotNone(result)
        self.assertEqual(result["meter_id"], 1)
        self.assertEqual(result["power_kw"], 2.5)

    def test_inactive_meter_is_filtered(self):
        """Inactive reading should return None."""
        event = {
            "meter_id": 2,
            "category": "SOLAR",
            "is_active": False,
            "power_kw": 3.0,
            "consumption_kwh": 0.5,
            "timestamp": "2026-11-03T12:00:00+00:00",
        }
        result = self.default_filter.process(event)
        self.assertIsNone(result)

    def test_below_threshold_is_filtered(self):
        """Reading with power_kw < min_power_kw should return None."""
        event = {
            "meter_id": 3,
            "category": "BATTERY",
            "is_active": True,
            "power_kw": 0.8,  # Below threshold 1.0
            "consumption_kwh": 0.1,
            "timestamp": "2026-11-03T12:00:00+00:00",
        }
        result = self.default_filter.process(event)
        self.assertIsNone(result)

    def test_exact_threshold_boundary_passes(self):
        """Reading with power_kw == min_power_kw should pass."""
        event = {
            "meter_id": 4,
            "category": "HVAC",
            "is_active": True,
            "power_kw": 1.0,  # Exact threshold
            "consumption_kwh": 0.4,
            "timestamp": "2026-11-03T12:00:00+00:00",
        }
        result = self.default_filter.process(event)
        self.assertIsNotNone(result)
        self.assertEqual(result["power_kw"], 1.0)

    def test_filter_inactive_disabled(self):
        """When filter_inactive=False, inactive meter with sufficient power should pass."""
        filter_allow_inactive = MeterFilter(min_power_kw=1.0, filter_inactive=False)
        event = {
            "meter_id": 5,
            "category": "SOLAR",
            "is_active": False,
            "power_kw": 2.0,
            "consumption_kwh": 0.7,
            "timestamp": "2026-11-03T12:00:00+00:00",
        }
        result = filter_allow_inactive.process(event)
        self.assertIsNotNone(result)
        self.assertEqual(result["meter_id"], 5)

    def test_category_filtering(self):
        """When allowed_categories is set, only matching categories pass."""
        category_filter = MeterFilter(min_power_kw=0.0, filter_inactive=True, allowed_categories=["HVAC", "SOLAR"])
        
        hvac_event = {"meter_id": 1, "category": "HVAC", "is_active": True, "power_kw": 1.5}
        battery_event = {"meter_id": 2, "category": "BATTERY", "is_active": True, "power_kw": 1.5}

        self.assertIsNotNone(category_filter.process(hvac_event))
        self.assertIsNone(category_filter.process(battery_event))

    def test_invalid_input_handling(self):
        """Non-dictionary inputs should return None gracefully."""
        self.assertIsNone(self.default_filter.process(None))
        self.assertIsNone(self.default_filter.process("not a dict"))
        self.assertIsNone(self.default_filter.process(123))

    def test_getters_and_setters_validation(self):
        """Verify encapsulation and validation rules."""
        f = MeterFilter()
        f.set_min_power_kw(2.5)
        self.assertEqual(f.get_min_power_kw(), 2.5)

        with self.assertRaises(ValueError):
            f.set_min_power_kw(-1.0)

        with self.assertRaises(TypeError):
            f.set_min_power_kw("invalid")

        f.set_filter_inactive(False)
        self.assertFalse(f.get_filter_inactive())

        f.set_allowed_categories(["hvac", "solar"])
        self.assertEqual(f.get_allowed_categories(), {"HVAC", "SOLAR"})

    def test_pipeline_integration_with_telemetry_generator(self):
        """Verify integration with Shaon's TelemetryGenerator and MeterReadingStream."""
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": False},  # inactive
            {"meter_id": 3, "category": "BATTERY", "is_active": True},
        ]
        generator = TelemetryGenerator(meters)
        readings = generator.generate(cycles=3, interval=0)
        stream = MeterReadingStream(readings)

        # Filter: requires active meters and min power 2.0 kW
        meter_filter = MeterFilter(min_power_kw=2.0, filter_inactive=True)

        filtered_events = list(meter_filter.process_stream(stream))

        # Assert every event that passed is active and >= 2.0 kW
        for event in filtered_events:
            self.assertTrue(event["is_active"], "Inactive meter was not filtered out")
            self.assertGreaterEqual(event["power_kw"], 2.0, "Low power reading was not filtered out")


if __name__ == "__main__":
    unittest.main()
