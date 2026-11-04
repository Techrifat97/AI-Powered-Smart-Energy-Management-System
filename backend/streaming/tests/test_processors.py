import subprocess
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.streaming.processors import (
    EnergyTransformer, MeterFilter, PeakTariffProcessor, StreamPipeline, StreamProcessor
)
from backend.streaming.source import MeterReadingStream, TelemetryGenerator


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "power_kw": 2.0, "consumption_kwh": 0.1,
            "timestamp": "2026-01-01T12:00:00+00:00"
        }

    def test_abstract_interface_and_polymorphism(self):
        with self.assertRaises(TypeError):
            StreamProcessor()

        class IncompleteProcessor(StreamProcessor):
            pass

        with self.assertRaises(TypeError):
            IncompleteProcessor()
        for processor in [MeterFilter(), EnergyTransformer(), PeakTariffProcessor()]:
            with self.subTest(processor=type(processor).__name__):
                self.assertIsInstance(processor, StreamProcessor)
                self.assertIsInstance(processor.process(self.event), dict)

    def test_filter_activity_and_power(self):
        categories = [
            ("HVAC", None), ("SOLAR", None),
            ("BATTERY", "CHARGING"), ("BATTERY", "DISCHARGING")
        ]
        for category, mode in categories:
            for active, power in [(False, 5), (True, 0.49), (True, 0.5), (True, 1)]:
                with self.subTest(category=category, mode=mode, active=active, power=power):
                    event = self.event.copy()
                    event.update(category=category, is_active=active,
                                 power_kw=power, consumption_kwh=100)
                    if mode is not None:
                        event["battery_mode"] = mode
                    result = MeterFilter(0.5).process(event)
                    if not active or power < 0.5:
                        self.assertIsNone(result)
                    else:
                        self.assertIs(result, event)

        self.event["power_kw"] = Decimal("0.1")
        self.assertIsNotNone(MeterFilter(0.1).process(self.event))

    def test_energy_contributions_and_decimal_accuracy(self):
        cases = [
            ("HVAC", None, "2"), ("LIGHTING", None, "2"), ("PLUG", None, "2"),
            ("SOLAR", None, "-2"), ("BATTERY", "CHARGING", "2"),
            ("BATTERY", "DISCHARGING", "-2")
        ]
        for category, mode, expected in cases:
            with self.subTest(category=category, mode=mode):
                event = self.event.copy()
                event.update(category=category, consumption_kwh=2)
                if mode is not None:
                    event["battery_mode"] = mode
                before = event.copy()
                result = EnergyTransformer().process(event)
                self.assertEqual(result["net_grid_contribution_kwh"], Decimal(expected))
                self.assertNotIn("net_grid_kwh", result)
                self.assertEqual(event, before)

        load = self.event.copy()
        load["consumption_kwh"] = Decimal("0.2")
        solar = self.event.copy()
        solar.update(category="SOLAR", consumption_kwh=Decimal("0.1"))
        transformer = EnergyTransformer()
        load_result = transformer.process(load)
        solar_result = transformer.process(solar)
        total = load_result["net_grid_contribution_kwh"] + solar_result["net_grid_contribution_kwh"]
        self.assertEqual(total, Decimal("0.1"))

    def test_peak_power_detection(self):
        categories = [
            ("HVAC", None, True), ("SOLAR", None, False),
            ("LIGHTING", None, True), ("PLUG", None, True),
            ("BATTERY", "CHARGING", True), ("BATTERY", "DISCHARGING", False)
        ]
        for category, mode, consumption in categories:
            for power in [3.99, 4.0, 4.01]:
                with self.subTest(category=category, mode=mode, power=power):
                    event = self.event.copy()
                    event.update(category=category, power_kw=power)
                    if mode is not None:
                        event["battery_mode"] = mode
                    before = event.copy()
                    result = PeakTariffProcessor(4).process(event)
                    self.assertIs(result["is_peak"], consumption and power > 4)
                    self.assertEqual(event, before)

        self.event["power_kw"] = Decimal("0.1")
        self.assertFalse(PeakTariffProcessor(0.1).process(self.event)["is_peak"])

    def test_invalid_event_data(self):
        cases = [
            ("meter_id", True, TypeError), ("meter_id", 0, ValueError),
            ("category", "UNKNOWN", ValueError), ("is_active", "False", TypeError),
            ("power_kw", -1, ValueError), ("power_kw", True, TypeError),
            ("power_kw", "2", TypeError), ("power_kw", float("inf"), ValueError),
            ("consumption_kwh", Decimal("NaN"), ValueError),
            ("consumption_kwh", -1, ValueError),
            ("timestamp", None, TypeError), ("timestamp", "invalid", ValueError),
            ("timestamp", "2026-01-01T12:00:00", ValueError),
            ("timestamp", "2026-01-01T12:00:00+02:00", ValueError)
        ]
        for processor in [MeterFilter(), EnergyTransformer(), PeakTariffProcessor()]:
            for event in [None, [], 42]:
                with self.subTest(processor=type(processor).__name__, event=event):
                    with self.assertRaises(TypeError):
                        processor.process(event)
            for field in self.event:
                with self.subTest(processor=type(processor).__name__, missing=field):
                    event = self.event.copy()
                    del event[field]
                    with self.assertRaises(ValueError):
                        processor.process(event)
            for field, value, expected_error in cases:
                with self.subTest(processor=type(processor).__name__, field=field, value=value):
                    event = self.event.copy()
                    event[field] = value
                    with self.assertRaises(expected_error):
                        processor.process(event)

        for mode in [None, "UNKNOWN"]:
            with self.subTest(mode=mode):
                event = self.event.copy()
                event.update(category="BATTERY", battery_mode=mode)
                with self.assertRaises(ValueError):
                    EnergyTransformer().process(event)

        event = self.event.copy()
        event.update(power_kw=3, consumption_kwh=0.05, measurement_seconds=60,
                     timestamp="2026-01-01T12:00:00Z")
        self.assertIsNotNone(MeterFilter().process(event))
        for field, value in [("measurement_seconds", 0), ("measurement_seconds", -1),
                             ("consumption_kwh", 1)]:
            with self.subTest(field=field, value=value):
                invalid = event.copy()
                invalid[field] = value
                with self.assertRaises(ValueError):
                    MeterFilter().process(invalid)

    def test_invalid_processor_settings(self):
        for processor_type in [MeterFilter, PeakTariffProcessor]:
            for value, expected_error in [
                (None, TypeError), (True, TypeError), ("0.5", TypeError),
                (-1, ValueError), (float("nan"), ValueError), (float("inf"), ValueError)
            ]:
                with self.subTest(processor=processor_type.__name__, value=value):
                    with self.assertRaises(expected_error):
                        processor_type(value)

        for stages in [[object()], [None]]:
            with self.subTest(stages=stages):
                with self.assertRaises(TypeError):
                    StreamPipeline(stages)
        with self.assertRaises(TypeError):
            MeterFilter() | 42
        pipeline = MeterFilter() | EnergyTransformer()
        with self.assertRaises(TypeError):
            pipeline | None
        with patch.object(pipeline.processors[0], "process", return_value=False):
            with self.assertRaises(TypeError):
                next(pipeline.run([self.event]))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "power_kw": 3, "consumption_kwh": 0.05,
            "timestamp": "2026-01-01T12:00:00+00:00"
        }

    def test_operator_composition_and_order(self):
        first = MeterFilter() | EnergyTransformer()
        second = StreamPipeline([PeakTariffProcessor(2)])
        pipeline = first | second
        self.assertEqual(len(first.processors), 2)
        self.assertEqual(len(second.processors), 1)
        self.assertEqual(len(pipeline.processors), 3)
        result = next(pipeline.run([self.event]))
        self.assertEqual(result["net_grid_contribution_kwh"], Decimal("0.05"))
        self.assertTrue(result["is_peak"])
        self.assertEqual(len((MeterFilter() | second).processors), 2)

        class OrderProcessor(StreamProcessor):
            def __init__(self, name):
                self.name = name

            def process(self, event):
                result = event.copy()
                result["order"] = event.get("order", "") + self.name
                return result

        ordered = OrderProcessor("A") | OrderProcessor("B") | OrderProcessor("C")
        self.assertEqual(next(ordered.run([self.event]))["order"], "ABC")

    def test_rejected_events_and_lazy_pipeline(self):
        consumed = []

        def events():
            for meter_id in [1, 2, 3]:
                consumed.append(meter_id)
                event = self.event.copy()
                event["meter_id"] = meter_id
                event["is_active"] = meter_id != 1
                yield event

        transformer = EnergyTransformer()
        pipeline = MeterFilter() | transformer | PeakTariffProcessor()
        with patch.object(transformer, "process", wraps=transformer.process) as process:
            results = pipeline.run(MeterReadingStream(events()))
            self.assertEqual(consumed, [])
            process.assert_not_called()
            self.assertEqual(next(results)["meter_id"], 2)
            self.assertEqual(consumed, [1, 2])
            process.assert_called_once()
            results.close()
        self.assertEqual(consumed, [1, 2])

    def test_empty_stream_and_pipeline(self):
        pipeline = MeterFilter() | EnergyTransformer()
        self.assertEqual(list(pipeline.run(iter([]))), [])
        self.assertEqual(list(StreamPipeline([]).run([self.event])), [self.event])


class DemoTests(unittest.TestCase):
    def test_end_to_end_stream_and_demo(self):
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": True},
            {"meter_id": 3, "category": "BATTERY", "is_active": True, "battery_mode": "CHARGING"},
            {"meter_id": 4, "category": "BATTERY", "is_active": True, "battery_mode": "DISCHARGING"},
            {"meter_id": 5, "category": "HVAC", "is_active": True},
            {"meter_id": 6, "category": "HVAC", "is_active": False}
        ]
        pipeline = MeterFilter() | EnergyTransformer() | PeakTariffProcessor(2)
        with patch("backend.streaming.source.random.uniform", side_effect=[3, 1.8, 0.6, 4.8, 0.2, 5]):
            stream = MeterReadingStream(TelemetryGenerator(meters).generate())
            results = list(pipeline.run(stream))
        self.assertEqual(len(results), 4)
        expected = [Decimal("0.05"), Decimal("-0.03"), Decimal("0.01"), Decimal("-0.08")]
        total = Decimal("0")
        for event, contribution in zip(results, expected):
            self.assertEqual(event["net_grid_contribution_kwh"], contribution)
            total += contribution
        self.assertEqual(total, Decimal("-0.05"))
        self.assertTrue(results[0]["is_peak"])
        self.assertFalse(results[3]["is_peak"])

        result = subprocess.run(
            [sys.executable, "-m", "backend.streaming.demo", "--cycles", "2",
             "--interval", "0", "--seed", "25"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CHARGING", result.stdout)
        self.assertIn("DISCHARGING", result.stdout)
        self.assertIn("net contribution=", result.stdout)
        self.assertIn("Generated 10; accepted 7; filtered 3.", result.stdout)

        invalid = subprocess.run(
            [sys.executable, "-m", "backend.streaming.demo", "--cycles", "-1", "--interval", "0"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("Cycles cannot be negative", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
