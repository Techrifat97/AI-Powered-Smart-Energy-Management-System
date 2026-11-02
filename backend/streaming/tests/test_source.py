
import unittest

from backend.streaming.source import MeterReadingStream, TelemetryGenerator


class TestMeterReadingStream(unittest.TestCase):

    def test_readings(self):
        events = [10, 20, 30]
        stream = MeterReadingStream(events)
        self.assertEqual(list(stream), events)

    def test_empty_stream(self):
        stream = MeterReadingStream([])
        self.assertEqual(list(stream), [])


class TestTelemetryGenerator(unittest.TestCase):

    def test_generate_readings(self):
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": False}
        ]
        generator = TelemetryGenerator(meters)
        readings = list(generator.generate())
        self.assertEqual(len(readings), 2)
        self.assertEqual(readings[0]["category"], "HVAC")
        self.assertEqual(readings[1]["is_active"], False)

    def test_multiple_cycles(self):
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": True},
            {"meter_id": 3, "category": "BATTERY", "is_active": False}
        ]

        generator = TelemetryGenerator(meters)
        readings = list(generator.generate(cycles=2, interval=0))

        self.assertEqual(len(readings), 6)
        self.assertEqual(readings[0]["meter_id"], 1)
        self.assertEqual(readings[3]["meter_id"], 1)
    
    def test_fifty_readings(self):
        meters = []

        for meter_id in range(1, 11):
            meter = {
                "meter_id": meter_id,
                "category": "HVAC",
                "is_active": True
            }
            meters.append(meter)

        generator = TelemetryGenerator(meters)
        readings = list(generator.generate(cycles=5, interval=0))

        self.assertEqual(len(readings), 50)
        self.assertEqual(readings[0]["meter_id"], 1)
        self.assertEqual(readings[10]["meter_id"], 1)
        self.assertEqual(readings[49]["meter_id"], 10)


if __name__ == "__main__":
    unittest.main()
