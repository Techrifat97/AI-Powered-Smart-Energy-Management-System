import unittest
from datetime import datetime, timezone
from unittest.mock import call, patch

from backend.streaming.source import MeterReadingStream, TelemetryGenerator


class TestMeterReadingStream(unittest.TestCase):

    def test_readings(self):
        for events in [[10, 20, 30], []]:
            with self.subTest(events=events):
                stream = MeterReadingStream(events)
                self.assertEqual(list(stream), events)

    def test_iterator_stays_exhausted(self):
        stream = MeterReadingStream([10])
        self.assertIs(iter(stream), stream)
        self.assertEqual(next(stream), 10)
        with self.assertRaises(StopIteration):
            next(stream)
        with self.assertRaises(StopIteration):
            next(stream)
        self.assertEqual(list(stream), [])

    def test_generator_events_are_consumed_lazily(self):
        consumed = []

        def events():
            for number in [10, 20]:
                consumed.append(number)
                yield number

        stream = MeterReadingStream(events())
        self.assertEqual(consumed, [])
        self.assertEqual(next(stream), 10)
        self.assertEqual(consumed, [10])
        self.assertEqual(list(stream), [20])
        self.assertEqual(consumed, [10, 20])

    def test_non_iterable_events_are_rejected(self):
        for events in [None, 42]:
            with self.subTest(events=events):
                with self.assertRaises(TypeError):
                    MeterReadingStream(events)


class TestTelemetryGenerator(unittest.TestCase):

    def setUp(self):
        self.meter = {"meter_id": 1, "category": "HVAC", "is_active": True}

    def test_generate_readings(self):
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": False},
            {"meter_id": 3, "category": "BATTERY", "is_active": True}
        ]
        generator = TelemetryGenerator(meters)
        readings = list(generator.generate())
        self.assertEqual(len(readings), 3)
        for meter, reading in zip(meters, readings):
            self.assertEqual(reading["meter_id"], meter["meter_id"])
            self.assertEqual(reading["category"], meter["category"])
            self.assertIs(reading["is_active"], meter["is_active"])

    def test_multiple_cycles(self):
        for meter_count, cycles in [(3, 2), (10, 5)]:
            with self.subTest(meter_count=meter_count, cycles=cycles):
                meters = []
                expected_ids = []
                for meter_id in range(1, meter_count + 1):
                    meter = self.meter.copy()
                    meter["meter_id"] = meter_id
                    meters.append(meter)
                    expected_ids.append(meter_id)

                generator = TelemetryGenerator(meters)
                readings = list(generator.generate(cycles=cycles))
                actual_ids = []
                for reading in readings:
                    actual_ids.append(reading["meter_id"])
                self.assertEqual(actual_ids, expected_ids * cycles)

    def test_iterator_meters_are_reused_for_every_cycle(self):
        generator = TelemetryGenerator(iter([self.meter]))
        readings = list(generator.generate(cycles=3))
        self.assertEqual(len(readings), 3)
        for reading in readings:
            self.assertEqual(reading["meter_id"], 1)
        self.assertEqual(len(list(generator.generate(cycles=2))), 2)

    def test_empty_generation_does_not_wait(self):
        for meters, cycles in [([], 3), ([self.meter], 0)]:
            with self.subTest(meters=meters, cycles=cycles):
                generator = TelemetryGenerator(meters)
                with patch("backend.streaming.source.time.sleep") as sleep:
                    self.assertEqual(list(generator.generate(cycles=cycles, interval=1)), [])
                    sleep.assert_not_called()

    def test_generated_event_format_and_values(self):
        generator = TelemetryGenerator([self.meter])
        with patch("backend.streaming.source.random.uniform",
                   side_effect=[1.234, 0.567]):
            reading = next(generator.generate())

        self.assertEqual(set(reading), {
            "meter_id", "category", "is_active", "power_kw",
            "consumption_kwh", "timestamp"
        })
        self.assertEqual(reading["meter_id"], 1)
        self.assertEqual(reading["category"], "HVAC")
        self.assertIs(reading["is_active"], True)
        self.assertEqual(reading["power_kw"], 1.23)
        self.assertEqual(reading["consumption_kwh"], 0.57)
        timestamp = datetime.fromisoformat(reading["timestamp"])
        self.assertEqual(timestamp.tzinfo, timezone.utc)

        for reading in generator.generate(cycles=10):
            self.assertIsInstance(reading["power_kw"], float)
            self.assertIsInstance(reading["consumption_kwh"], float)
            self.assertGreaterEqual(reading["power_kw"], 0)
            self.assertLessEqual(reading["power_kw"], 5)
            self.assertGreaterEqual(reading["consumption_kwh"], 0)
            self.assertLessEqual(reading["consumption_kwh"], 2)

    def test_generated_events_pass_through_stream_lazily(self):
        generator = TelemetryGenerator([self.meter])
        with patch("backend.streaming.source.random.uniform", return_value=1) as uniform:
            stream = MeterReadingStream(generator.generate(cycles=2))
            uniform.assert_not_called()
            self.assertEqual(next(stream)["meter_id"], 1)
            self.assertEqual(uniform.call_count, 2)
            self.assertEqual(len(list(stream)), 1)
            self.assertEqual(uniform.call_count, 4)

    def test_waits_only_between_cycles(self):
        generator = TelemetryGenerator([self.meter, self.meter.copy()])
        with patch("backend.streaming.source.time.sleep") as sleep:
            readings = list(generator.generate(cycles=3, interval=0.5))
            self.assertEqual(len(readings), 6)
            self.assertEqual(sleep.call_args_list, [call(0.5), call(0.5)])

    def test_invalid_meter_data(self):
        for meters in [None, 42, [None], ["meter"], [42]]:
            with self.subTest(meters=meters):
                with self.assertRaises(TypeError):
                    TelemetryGenerator(meters)

        for field in ["meter_id", "category", "is_active"]:
            with self.subTest(field=field):
                meter = self.meter.copy()
                del meter[field]
                with self.assertRaises(ValueError):
                    TelemetryGenerator([meter])

    def test_invalid_meter_fields(self):
        cases = [
            ("meter_id", "1", TypeError),
            ("meter_id", 1.5, TypeError),
            ("meter_id", True, TypeError),
            ("meter_id", None, TypeError),
            ("meter_id", 0, ValueError),
            ("meter_id", -1, ValueError),
            ("category", None, TypeError),
            ("category", 42, TypeError),
            ("category", "", ValueError),
            ("category", "   ", ValueError),
            ("is_active", "False", TypeError),
            ("is_active", 0, TypeError),
            ("is_active", 1, TypeError),
            ("is_active", None, TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                meter = self.meter.copy()
                meter[field] = value
                with self.assertRaises(expected_error):
                    TelemetryGenerator([meter])

    def test_invalid_cycles(self):
        generator = TelemetryGenerator([self.meter])
        cases = [("2", TypeError), (1.5, TypeError), (True, TypeError),
                 (None, TypeError), (-1, ValueError)]
        for cycles, expected_error in cases:
            with self.subTest(cycles=cycles):
                with self.assertRaises(expected_error):
                    next(generator.generate(cycles=cycles))

    def test_invalid_intervals(self):
        generator = TelemetryGenerator([self.meter])
        cases = [
            ("1", TypeError), (True, TypeError), (None, TypeError),
            (-1, ValueError), (float("nan"), ValueError), (float("inf"), ValueError)
        ]
        for interval, expected_error in cases:
            with self.subTest(interval=interval):
                with self.assertRaises(expected_error):
                    next(generator.generate(interval=interval))


if __name__ == "__main__":
    unittest.main()
