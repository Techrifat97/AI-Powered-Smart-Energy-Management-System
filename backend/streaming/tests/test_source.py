import unittest
from datetime import datetime, timezone
from unittest.mock import call, patch

from backend.streaming.source import MeterReadingStream, TelemetryGenerator


class TestMeterReadingStream(unittest.TestCase):
    def test_iterator_protocol_and_lazy_generation(self):
        for events in [[10, 20, 30], []]:
            with self.subTest(events=events):
                stream = MeterReadingStream(events)
                self.assertIs(iter(stream), stream)
                for expected in events:
                    self.assertEqual(next(stream), expected)
                for attempt in range(2):
                    with self.assertRaises(StopIteration):
                        next(stream)
                self.assertEqual(list(stream), [])

        for events in [None, 42]:
            with self.subTest(events=events):
                with self.assertRaises(TypeError):
                    MeterReadingStream(events)

        meters = [{"meter_id": 1, "category": "HVAC", "is_active": True}]
        with patch("backend.streaming.source.random.uniform", return_value=2.0) as power:
            readings = TelemetryGenerator(meters).generate(cycles=2)
            stream = MeterReadingStream(readings)
            power.assert_not_called()
            self.assertEqual(next(stream)["meter_id"], 1)
            self.assertEqual(power.call_count, 1)
            self.assertEqual(len(list(stream)), 1)
            self.assertEqual(power.call_count, 2)


class TestTelemetryGenerator(unittest.TestCase):
    def setUp(self):
        self.meter = {"meter_id": 1, "category": "HVAC", "is_active": True}
        power_patch = patch("backend.streaming.source.random.uniform", return_value=2.0)
        mode_patch = patch("backend.streaming.source.random.choice", return_value="CHARGING")
        power_patch.start()
        mode_patch.start()
        self.addCleanup(power_patch.stop)
        self.addCleanup(mode_patch.stop)

    def test_telemetry_generation_and_meter_reuse(self):
        meters = [
            self.meter.copy(),
            {"meter_id": 2, "category": "SOLAR", "is_active": False},
            {"meter_id": 3, "category": "BATTERY", "is_active": True, "battery_mode": "CHARGING"},
            {"meter_id": 4, "category": "BATTERY", "is_active": True, "battery_mode": "DISCHARGING"},
            {"meter_id": 5, "category": "BATTERY", "is_active": True}
        ]
        for meter_id in range(6, 11):
            meter = self.meter.copy()
            meter["meter_id"] = meter_id
            meters.append(meter)

        generator = TelemetryGenerator(iter(meters))
        readings = list(generator.generate(cycles=5))
        self.assertEqual(len(readings), 50)
        self.assertEqual(set(readings[0]), {
            "meter_id", "category", "is_active", "power_kw",
            "consumption_kwh", "measurement_seconds", "timestamp"
        })
        for cycle in range(5):
            for index, meter in enumerate(meters):
                with self.subTest(cycle=cycle, meter_id=meter["meter_id"]):
                    reading = readings[cycle * len(meters) + index]
                    self.assertEqual(reading["meter_id"], meter["meter_id"])
                    self.assertEqual(reading["category"], meter["category"])
                    self.assertIs(reading["is_active"], meter["is_active"])
                    self.assertEqual(reading["power_kw"], 2.0)
                    self.assertIsInstance(reading["consumption_kwh"], float)
                    self.assertEqual(reading["measurement_seconds"], 60)
                    timestamp = datetime.fromisoformat(reading["timestamp"])
                    self.assertEqual(timestamp.tzinfo, timezone.utc)
                    if meter["category"] == "BATTERY":
                        self.assertEqual(reading["battery_mode"], meter.get("battery_mode", "CHARGING"))
        self.assertEqual(len(list(generator.generate())), 10)

    def test_energy_calculation_and_timing(self):
        for seconds in [30, 60, 3600]:
            for interval in [0, 1]:
                with self.subTest(seconds=seconds, interval=interval):
                    generator = TelemetryGenerator([self.meter], measurement_seconds=seconds)
                    with patch("backend.streaming.source.time.sleep") as sleep:
                        readings = list(generator.generate(cycles=3, interval=interval))
                    self.assertEqual(len(readings), 3)
                    for reading in readings:
                        self.assertAlmostEqual(reading["consumption_kwh"], 2.0 * seconds / 3600)
                        self.assertEqual(reading["measurement_seconds"], seconds)
                    expected_calls = [call(interval), call(interval)] if interval else []
                    self.assertEqual(sleep.call_args_list, expected_calls)

        for meters, cycles in [([], 3), ([self.meter], 0)]:
            with self.subTest(meters=meters, cycles=cycles):
                generator = TelemetryGenerator(meters)
                with patch("backend.streaming.source.time.sleep") as sleep:
                    self.assertEqual(list(generator.generate(cycles=cycles, interval=1)), [])
                    sleep.assert_not_called()

        with patch("backend.streaming.source.random.uniform", return_value=1.234):
            reading = next(TelemetryGenerator([self.meter]).generate())
        self.assertEqual(reading["power_kw"], 1.23)
        self.assertEqual(reading["consumption_kwh"], 0.0205)

    def test_invalid_meter_data(self):
        for meters in [None, 42, [None], ["meter"], [42]]:
            with self.subTest(meters=meters):
                with self.assertRaises(TypeError):
                    TelemetryGenerator(meters)
        for field in ["meter_id", "category", "is_active"]:
            with self.subTest(missing=field):
                meter = self.meter.copy()
                del meter[field]
                with self.assertRaises(ValueError):
                    TelemetryGenerator([meter])

        cases = [
            ("meter_id", "1", TypeError), ("meter_id", 1.5, TypeError),
            ("meter_id", True, TypeError), ("meter_id", None, TypeError),
            ("meter_id", 0, ValueError), ("meter_id", -1, ValueError),
            ("category", None, TypeError), ("category", 42, TypeError),
            ("category", "", ValueError), ("category", "   ", ValueError),
            ("is_active", "False", TypeError), ("is_active", 0, TypeError),
            ("is_active", 1, TypeError), ("is_active", None, TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                meter = self.meter.copy()
                meter[field] = value
                with self.assertRaises(expected_error):
                    TelemetryGenerator([meter])
        for mode in [None, "UNKNOWN"]:
            with self.subTest(mode=mode):
                meter = self.meter.copy()
                meter.update(category="BATTERY", battery_mode=mode)
                with self.assertRaises(ValueError):
                    TelemetryGenerator([meter])

    def test_invalid_generation_settings(self):
        generator = TelemetryGenerator([self.meter])
        for cycles, expected_error in [
            ("2", TypeError), (1.5, TypeError), (True, TypeError),
            (None, TypeError), (-1, ValueError)
        ]:
            with self.subTest(cycles=cycles):
                with self.assertRaises(expected_error):
                    next(generator.generate(cycles=cycles))

        for interval, expected_error in [
            ("1", TypeError), (True, TypeError), (None, TypeError),
            (-1, ValueError), (float("nan"), ValueError), (float("inf"), ValueError)
        ]:
            with self.subTest(interval=interval):
                with self.assertRaises(expected_error):
                    next(generator.generate(interval=interval))

        for seconds, expected_error in [
            ("60", TypeError), (True, TypeError), (None, TypeError),
            (0, ValueError), (-1, ValueError),
            (float("nan"), ValueError), (float("inf"), ValueError)
        ]:
            with self.subTest(seconds=seconds):
                with self.assertRaises(expected_error):
                    TelemetryGenerator([self.meter], measurement_seconds=seconds)


if __name__ == "__main__":
    unittest.main()
