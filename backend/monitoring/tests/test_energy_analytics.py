import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.monitoring.domain.building import Building
from backend.monitoring.domain.consumption_summary import ConsumptionSummary
from backend.monitoring.domain.energy_reading import EnergyReading
from backend.monitoring.domain.meter import Meter
from backend.monitoring.services.energy_analytics_service import EnergyAnalyticsService
from backend.monitoring.services.reading_ingestion_service import ReadingIngestionService
from backend.monitoring.services.reading_validator import ReadingValidator


class ConsumptionSummaryTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.end = self.start + timedelta(days=1)
        self.values = {
            "building_id": 1, "start": self.start, "end": self.end,
            "gross_load_kwh": "0.3", "solar_generation_kwh": "0.1",
            "net_grid_kwh": "0.2", "category_totals_kwh": {"HVAC": "0.3"},
            "peak_kw": 2.5, "reading_count": 2
        }

    def test_constructor_getters_and_serialization(self):
        summary = ConsumptionSummary(**self.values)
        self.assertEqual(summary.get_building_id(), 1)
        self.assertEqual(summary.get_start(), self.start)
        self.assertEqual(summary.get_end(), self.end)
        self.assertEqual(summary.get_gross_load(), Decimal("0.3"))
        self.assertEqual(summary.get_solar_generation(), Decimal("0.1"))
        self.assertEqual(summary.get_net_grid(), Decimal("0.2"))
        self.assertEqual(summary.get_peak(), 2.5)
        self.assertEqual(summary.get_reading_count(), 2)
        self.assertEqual(summary.get_category_totals(), {
            "HVAC": Decimal("0.3"), "LIGHTING": Decimal("0"), "PLUG": Decimal("0")
        })
        serialized = summary.to_dict()
        self.assertEqual(serialized, {
            "building_id": 1, "start": self.start.isoformat(),
            "end": self.end.isoformat(), "gross_load_kwh": "0.3",
            "solar_generation_kwh": "0.1", "net_grid_kwh": "0.2",
            "category_totals_kwh": {"HVAC": "0.3", "LIGHTING": "0", "PLUG": "0"},
            "peak_kw": 2.5, "reading_count": 2
        })
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)

    def test_category_dictionaries_are_copied(self):
        summary = ConsumptionSummary(**self.values)
        self.values["category_totals_kwh"]["HVAC"] = "999"
        categories = summary.get_category_totals()
        categories["HVAC"] = Decimal("999")
        serialized = summary.to_dict()
        serialized["category_totals_kwh"]["HVAC"] = "999"
        self.assertEqual(summary.get_category_totals()["HVAC"], Decimal("0.3"))

    def test_negative_net_grid_represents_export(self):
        self.values["solar_generation_kwh"] = "0.5"
        self.values["net_grid_kwh"] = "-0.2"
        summary = ConsumptionSummary(**self.values)
        self.assertEqual(summary.get_net_grid(), Decimal("-0.2"))

    def test_invalid_types_and_values(self):
        cases = [
            ("building_id", True, TypeError),
            ("building_id", "1", TypeError),
            ("gross_load_kwh", "-1", ValueError),
            ("gross_load_kwh", "NaN", ValueError),
            ("gross_load_kwh", "invalid", ValueError),
            ("gross_load_kwh", None, TypeError),
            ("solar_generation_kwh", "-1", ValueError),
            ("solar_generation_kwh", "Infinity", ValueError),
            ("net_grid_kwh", "NaN", ValueError),
            ("net_grid_kwh", "999", ValueError),
            ("category_totals_kwh", [], TypeError),
            ("category_totals_kwh", {"SOLAR": "0.3"}, ValueError),
            ("category_totals_kwh", {"HVAC": "-1"}, ValueError),
            ("category_totals_kwh", {"HVAC": "0.4"}, ValueError),
            ("peak_kw", float("nan"), ValueError),
            ("peak_kw", float("inf"), ValueError),
            ("peak_kw", True, TypeError),
            ("reading_count", -1, ValueError),
            ("reading_count", 1.5, TypeError),
            ("reading_count", True, TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                values = self.values.copy()
                values[field] = value
                with self.assertRaises(expected_error):
                    ConsumptionSummary(**values)

    def test_invalid_time_intervals(self):
        cases = [
            (self.start, self.start, ValueError),
            (self.end, self.start, ValueError),
            (self.start.replace(tzinfo=None), self.end, ValueError),
            (self.start, self.end.replace(tzinfo=None), ValueError),
            (self.start.astimezone(timezone(timedelta(hours=2))), self.end, ValueError),
            ("2026-01-01", self.end, TypeError)
        ]
        for start, end, expected_error in cases:
            with self.subTest(start=start, end=end):
                values = self.values.copy()
                values["start"] = start
                values["end"] = end
                with self.assertRaises(expected_error):
                    ConsumptionSummary(**values)


class EnergyAnalyticsServiceTests(unittest.TestCase):
    def setUp(self):
        self.building = Building(1, "Campus", "Dortmund", 2500, "University")
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.end = self.start + timedelta(days=1)
        self.meters = {}
        meter_id = 1
        for category in ["HVAC", "LIGHTING", "PLUG", "SOLAR"]:
            meter = Meter(meter_id, category, "kWh")
            self.meters[category] = meter
            self.building.add_meter(meter)
            meter_id += 1
        self.service = EnergyAnalyticsService()

    def add_reading(self, category, consumption, power, timestamp=None):
        if timestamp is None:
            timestamp = self.start
        meter = self.meters[category]
        reading = EnergyReading(len(meter.readings) + 1, timestamp, consumption, power, "MANUAL")
        meter.add_reading(reading)
        return reading

    def test_load_categories_solar_net_grid_and_individual_peak(self):
        self.add_reading("HVAC", "120", 80)
        self.add_reading("LIGHTING", "30", 20)
        self.add_reading("PLUG", "30", 15)
        self.add_reading("SOLAR", "40", 999)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertIsInstance(summary, ConsumptionSummary)
        self.assertEqual(summary.building_id, self.building.id)
        self.assertEqual(summary.gross_load_kwh, Decimal("180"))
        self.assertEqual(summary.solar_generation_kwh, Decimal("40"))
        self.assertEqual(summary.net_grid_kwh, Decimal("140"))
        self.assertEqual(summary.category_totals_kwh, {
            "HVAC": Decimal("120"), "LIGHTING": Decimal("30"), "PLUG": Decimal("30")
        })
        self.assertEqual(summary.peak_kw, 80.0)
        self.assertEqual(summary.reading_count, 4)

    def test_decimal_accuracy(self):
        self.add_reading("HVAC", "0.1", 1)
        self.add_reading("HVAC", "0.2", 2)
        self.add_reading("SOLAR", "0.05", 3)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.gross_load_kwh, Decimal("0.3"))
        self.assertEqual(summary.net_grid_kwh, Decimal("0.25"))
        self.assertIsInstance(summary.net_grid_kwh, Decimal)

    def test_time_range_includes_start_and_excludes_end(self):
        self.add_reading("HVAC", 100, 100, self.end)
        self.add_reading("HVAC", 1, 2, self.start)
        self.add_reading("HVAC", 100, 100, self.start - timedelta(seconds=1))
        self.add_reading("HVAC", 2, 3, self.end - timedelta(seconds=1))
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.gross_load_kwh, Decimal("3"))
        self.assertEqual(summary.reading_count, 2)
        self.assertEqual(summary.peak_kw, 3.0)

    def test_empty_building_and_empty_meters(self):
        empty = Building(2, "Empty", "Dortmund", 100, "Office")
        for building in [empty, self.building]:
            with self.subTest(building_id=building.id):
                summary = self.service.summarize(building, self.start, self.end)
                self.assertEqual(summary.gross_load_kwh, Decimal("0"))
                self.assertEqual(summary.solar_generation_kwh, Decimal("0"))
                self.assertEqual(summary.net_grid_kwh, Decimal("0"))
                self.assertEqual(summary.reading_count, 0)
                self.assertEqual(summary.peak_kw, 0.0)

    def test_solar_only_has_negative_net_grid_and_no_load_peak(self):
        self.add_reading("SOLAR", 5, 50)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.gross_load_kwh, Decimal("0"))
        self.assertEqual(summary.net_grid_kwh, Decimal("-5"))
        self.assertEqual(summary.peak_kw, 0.0)
        self.assertEqual(summary.reading_count, 1)

    def test_inactive_meters_and_invalid_legacy_readings_are_excluded(self):
        self.add_reading("HVAC", 1, 2)
        invalid = self.add_reading("HVAC", 50, 50)
        invalid.is_valid = False
        self.add_reading("HVAC", 50, 50, self.start.replace(tzinfo=None))
        corrupt = self.add_reading("HVAC", 50, 50)
        corrupt.consumption_kwh = Decimal("NaN")
        self.add_reading("LIGHTING", 100, 100)
        self.meters["LIGHTING"].set_status(False)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.gross_load_kwh, Decimal("1"))
        self.assertEqual(summary.reading_count, 1)
        self.assertEqual(summary.peak_kw, 2.0)

    def test_summary_does_not_change_original_readings(self):
        reading = self.add_reading("HVAC", "1.20", 3)
        before = reading.to_dict()
        meters = self.building.meters.copy()
        readings = self.meters["HVAC"].readings.copy()
        self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(reading.to_dict(), before)
        self.assertEqual(self.building.meters, meters)
        self.assertEqual(self.meters["HVAC"].readings, readings)

    def test_peak_uses_the_largest_finite_load_power_even_when_negative(self):
        self.add_reading("HVAC", 1, -5)
        self.add_reading("HVAC", 1, -2)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.peak_kw, -2.0)

    def test_invalid_building_and_time_range(self):
        with self.assertRaises(TypeError):
            self.service.summarize(None, self.start, self.end)
        cases = [
            (self.start, self.start, ValueError),
            (self.end, self.start, ValueError),
            (self.start.replace(tzinfo=None), self.end, ValueError),
            (self.start, self.end.replace(tzinfo=None), ValueError),
            (self.start, self.end.astimezone(timezone(timedelta(hours=1))), ValueError),
            (None, self.end, TypeError)
        ]
        for start, end, expected_error in cases:
            with self.subTest(start=start, end=end):
                with self.assertRaises(expected_error):
                    self.service.summarize(self.building, start, end)

    def test_event_ingestion_batch_ingestion_and_summary_work_together(self):
        ingestion = ReadingIngestionService(ReadingValidator())
        event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "consumption_kwh": 0.1, "power_kw": 4.5,
            "timestamp": self.start.isoformat()
        }
        ingestion.ingest_event(self.meters["HVAC"], event, 1)
        reading = EnergyReading(2, self.start + timedelta(hours=1), "0.2", 3, "MANUAL")
        ingestion.ingest_batch(self.meters["HVAC"], [reading])
        self.add_reading("SOLAR", "0.05", 99)
        summary = self.service.summarize(self.building, self.start, self.end)
        self.assertEqual(summary.net_grid_kwh, Decimal("0.25"))
        self.assertEqual(summary.peak_kw, 4.5)
        self.assertEqual(summary.reading_count, 3)


if __name__ == "__main__":
    unittest.main()
