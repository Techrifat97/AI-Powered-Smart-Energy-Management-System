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

    def test_abstract_class_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            StreamProcessor()

        class IncompleteProcessor(StreamProcessor):
            pass

        with self.assertRaises(TypeError):
            IncompleteProcessor()

    def test_inheritance_and_polymorphism(self):
        processors = [MeterFilter(), EnergyTransformer(), PeakTariffProcessor()]
        for processor in processors:
            with self.subTest(processor=type(processor).__name__):
                self.assertIsInstance(processor, StreamProcessor)
                self.assertIsInstance(processor.process(self.event), dict)

    def test_invalid_thresholds(self):
        cases = [
            (None, TypeError), (True, TypeError), ("0.5", TypeError),
            (-1, ValueError), (float("nan"), ValueError), (float("inf"), ValueError)
        ]
        for processor_type in [MeterFilter, PeakTariffProcessor]:
            for value, expected_error in cases:
                with self.subTest(processor=processor_type.__name__, value=value):
                    with self.assertRaises(expected_error):
                        processor_type(value)

    def test_filter_rejects_inactive_meters(self):
        for category in ["HVAC", "SOLAR", "BATTERY"]:
            with self.subTest(category=category):
                event = self.event.copy()
                event.update(category=category, is_active=False, battery_mode="CHARGING")
                self.assertIsNone(MeterFilter(0).process(event))

    def test_filter_uses_power_and_includes_the_threshold(self):
        for category, mode in [("HVAC", None), ("SOLAR", None),
                               ("BATTERY", "CHARGING"), ("BATTERY", "DISCHARGING")]:
            for power in [0.49, 0.5, 1]:
                with self.subTest(category=category, mode=mode, power=power):
                    event = self.event.copy()
                    event.update(category=category, power_kw=power, consumption_kwh=100)
                    if mode is not None:
                        event["battery_mode"] = mode
                    result = MeterFilter(0.5).process(event)
                    if power < 0.5:
                        self.assertIsNone(result)
                    else:
                        self.assertIs(result, event)

    def test_energy_contribution_signs(self):
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
                result = EnergyTransformer().process(event)
                self.assertEqual(result["net_grid_contribution_kwh"], Decimal(expected))
                self.assertNotIn("net_grid_kwh", result)

    def test_load_and_solar_balance_uses_decimal(self):
        load = self.event.copy()
        load["consumption_kwh"] = Decimal("0.2")
        solar = self.event.copy()
        solar.update(category="SOLAR", consumption_kwh=Decimal("0.1"))
        transformer = EnergyTransformer()
        net_energy = (
            transformer.process(load)["net_grid_contribution_kwh"]
            + transformer.process(solar)["net_grid_contribution_kwh"]
        )
        self.assertEqual(net_energy, Decimal("0.1"))

    def test_processors_do_not_change_the_original_event(self):
        before = self.event.copy()
        transformed = EnergyTransformer().process(self.event)
        result = PeakTariffProcessor(1).process(transformed)
        self.assertEqual(self.event, before)
        self.assertNotIn("is_peak", transformed)
        self.assertTrue(result["is_peak"])

    def test_peak_is_strictly_above_the_threshold_for_consumption_only(self):
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
                    result = PeakTariffProcessor(4).process(event)
                    self.assertIs(result["is_peak"], consumption and power > 4)

    def test_decimal_power_threshold_comparisons_are_exact(self):
        self.event["power_kw"] = Decimal("0.1")
        self.assertIsNotNone(MeterFilter(0.1).process(self.event))
        self.assertFalse(PeakTariffProcessor(0.1).process(self.event)["is_peak"])

    def test_invalid_event_types_and_missing_fields(self):
        for processor in [MeterFilter(), EnergyTransformer(), PeakTariffProcessor()]:
            with self.subTest(processor=type(processor).__name__):
                for event in [None, [], 42]:
                    with self.assertRaises(TypeError):
                        processor.process(event)
                for field in self.event:
                    event = self.event.copy()
                    del event[field]
                    with self.assertRaises(ValueError):
                        processor.process(event)

    def test_invalid_event_values(self):
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
            for field, value, expected_error in cases:
                with self.subTest(processor=type(processor).__name__, field=field, value=value):
                    event = self.event.copy()
                    event[field] = value
                    with self.assertRaises(expected_error):
                        processor.process(event)

    def test_battery_direction_is_required(self):
        self.event["category"] = "BATTERY"
        for mode in [None, "UNKNOWN"]:
            with self.subTest(mode=mode):
                self.event["battery_mode"] = mode
                with self.assertRaises(ValueError):
                    EnergyTransformer().process(self.event)

    def test_measurement_metadata_must_match_energy(self):
        self.event.update(power_kw=3, consumption_kwh=0.05, measurement_seconds=60)
        self.assertIsNotNone(MeterFilter().process(self.event))
        self.event["timestamp"] = "2026-01-01T12:00:00Z"
        self.assertIsNotNone(MeterFilter().process(self.event))
        for field, value in [("measurement_seconds", 0), ("measurement_seconds", -1),
                             ("consumption_kwh", 1)]:
            with self.subTest(field=field, value=value):
                event = self.event.copy()
                event[field] = value
                with self.assertRaises(ValueError):
                    MeterFilter().process(event)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "power_kw": 3, "consumption_kwh": 0.05,
            "timestamp": "2026-01-01T12:00:00+00:00"
        }
        self.pipeline = MeterFilter() | EnergyTransformer() | PeakTariffProcessor(2)

    def test_operator_composition_and_results(self):
        self.assertIsInstance(self.pipeline, StreamPipeline)
        self.assertEqual(len(self.pipeline.processors), 3)
        result = next(self.pipeline.run([self.event]))
        self.assertEqual(result["net_grid_contribution_kwh"], Decimal("0.05"))
        self.assertTrue(result["is_peak"])

    def test_pipeline_composition_does_not_change_existing_pipelines(self):
        first = MeterFilter() | EnergyTransformer()
        second = StreamPipeline([PeakTariffProcessor()])
        combined = first | second
        self.assertEqual(len(first.processors), 2)
        self.assertEqual(len(second.processors), 1)
        self.assertEqual(len(combined.processors), 3)
        prepended = MeterFilter() | second
        self.assertEqual(len(prepended.processors), 2)

    def test_invalid_stages_and_invalid_processor_result(self):
        for processors in [[object()], [None]]:
            with self.subTest(processors=processors):
                with self.assertRaises(TypeError):
                    StreamPipeline(processors)
        with self.assertRaises(TypeError):
            MeterFilter() | 42
        with self.assertRaises(TypeError):
            self.pipeline | None
        with patch.object(self.pipeline.processors[0], "process", return_value=False):
            with self.assertRaises(TypeError):
                next(self.pipeline.run([self.event]))

    def test_custom_processors_run_in_order(self):
        class OrderProcessor(StreamProcessor):
            def __init__(self, name):
                self.name = name

            def process(self, event):
                result = event.copy()
                result["order"] = event.get("order", "") + self.name
                return result

        pipeline = OrderProcessor("A") | OrderProcessor("B") | OrderProcessor("C")
        self.assertEqual(next(pipeline.run([self.event]))["order"], "ABC")

    def test_rejected_events_do_not_reach_later_processors(self):
        self.event["is_active"] = False
        transformer = self.pipeline.processors[1]
        with patch.object(transformer, "process", wraps=transformer.process) as process:
            self.assertEqual(list(self.pipeline.run([self.event])), [])
            process.assert_not_called()

    def test_pipeline_is_lazy_and_does_not_prefetch_events(self):
        consumed = []

        def events():
            for meter_id in [1, 2, 3]:
                consumed.append(meter_id)
                event = self.event.copy()
                event["meter_id"] = meter_id
                yield event

        results = self.pipeline.run(MeterReadingStream(events()))
        self.assertEqual(consumed, [])
        self.assertEqual(next(results)["meter_id"], 1)
        self.assertEqual(consumed, [1])
        self.assertEqual(next(results)["meter_id"], 2)
        self.assertEqual(consumed, [1, 2])
        results.close()
        self.assertEqual(consumed, [1, 2])

    def test_empty_stream_and_empty_pipeline(self):
        self.assertEqual(list(self.pipeline.run(iter([]))), [])
        self.assertEqual(list(StreamPipeline([]).run([self.event])), [self.event])

    def test_complete_generated_stream(self):
        meters = [
            {"meter_id": 1, "category": "HVAC", "is_active": True},
            {"meter_id": 2, "category": "SOLAR", "is_active": True},
            {"meter_id": 3, "category": "BATTERY", "is_active": True, "battery_mode": "CHARGING"},
            {"meter_id": 4, "category": "BATTERY", "is_active": True, "battery_mode": "DISCHARGING"},
            {"meter_id": 5, "category": "HVAC", "is_active": True},
            {"meter_id": 6, "category": "HVAC", "is_active": False}
        ]
        with patch("backend.streaming.source.random.uniform", side_effect=[3, 1.8, 0.6, 4.8, 0.2, 5]):
            source = TelemetryGenerator(meters).generate()
            results = list(self.pipeline.run(MeterReadingStream(source)))
        self.assertEqual(len(results), 4)
        expected = [Decimal("0.05"), Decimal("-0.03"), Decimal("0.01"), Decimal("-0.08")]
        total = Decimal("0")
        for event, contribution in zip(results, expected):
            self.assertEqual(event["net_grid_contribution_kwh"], contribution)
            total += contribution
        self.assertEqual(total, Decimal("-0.05"))
        self.assertTrue(results[0]["is_peak"])
        self.assertFalse(results[3]["is_peak"])


class DemoTests(unittest.TestCase):
    def test_demo_finishes_and_reports_processed_events(self):
        result = subprocess.run(
            [sys.executable, "-m", "backend.streaming.demo", "--cycles", "2",
             "--interval", "0", "--seed", "25"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("net contribution=", result.stdout)
        self.assertIn("CHARGING", result.stdout)
        self.assertIn("DISCHARGING", result.stdout)
        self.assertIn("Generated 10;", result.stdout)

    def test_demo_explains_invalid_settings(self):
        result = subprocess.run(
            [sys.executable, "-m", "backend.streaming.demo", "--cycles", "-1", "--interval", "0"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cycles cannot be negative", result.stderr)


if __name__ == "__main__":
    unittest.main()
