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
    def test_summary_totals_serialization_and_validation(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        values = {
            "building_id": 1, "start": start, "end": end,
            "gross_load_kwh": Decimal("0.1") + Decimal("0.2"),
            "solar_generation_kwh": "0.1", "net_grid_kwh": "0.2",
            "category_totals_kwh": {"HVAC": "0.3"},
            "peak_kw": 2.5, "reading_count": 2
        }
        summary = ConsumptionSummary(**values)
        self.assertEqual(summary.get_building_id(), 1)
        self.assertEqual(summary.get_start(), start)
        self.assertEqual(summary.get_end(), end)
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
            "building_id": 1, "start": start.isoformat(), "end": end.isoformat(),
            "gross_load_kwh": "0.3", "solar_generation_kwh": "0.1",
            "net_grid_kwh": "0.2", "category_totals_kwh": {
                "HVAC": "0.3", "LIGHTING": "0", "PLUG": "0"
            }, "peak_kw": 2.5, "reading_count": 2
        })
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
        export = ConsumptionSummary(**dict(values, solar_generation_kwh="0.5", net_grid_kwh="-0.2"))
        self.assertEqual(export.get_net_grid(), Decimal("-0.2"))

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
            ("reading_count", True, TypeError),
            ("end", start, ValueError),
            ("end", start - timedelta(seconds=1), ValueError),
            ("start", start.replace(tzinfo=None), ValueError),
            ("end", end.replace(tzinfo=None), ValueError),
            ("start", start.astimezone(timezone(timedelta(hours=2))), ValueError),
            ("start", "2026-01-01", TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                invalid = values.copy()
                invalid[field] = value
                with self.assertRaises(expected_error):
                    ConsumptionSummary(**invalid)

        # Neither the input dictionary nor returned dictionaries share storage.
        values["category_totals_kwh"]["HVAC"] = "999"
        categories = summary.get_category_totals()
        categories["HVAC"] = Decimal("999")
        serialized["category_totals_kwh"]["HVAC"] = "999"
        self.assertEqual(summary.get_category_totals()["HVAC"], Decimal("0.3"))


class EnergyAnalyticsServiceTests(unittest.TestCase):
    def test_analytics_summaries_filtering_and_ingestion(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        service = EnergyAnalyticsService()
        # Each row contains readings, then expected load, solar, net, peak and count.
        # A reading is (category, energy, power, timestamp).
        cases = [
            ("all categories", [
                ("HVAC", "120", 80, start), ("LIGHTING", "30", 20, start),
                ("PLUG", "30", 15, start), ("SOLAR", "40", 999, start)
            ], "180", "40", "140", 80.0, 4),
            ("time boundaries", [
                ("HVAC", 100, 100, end), ("HVAC", 1, 2, start),
                ("HVAC", 100, 100, start - timedelta(seconds=1)),
                ("HVAC", 2, 3, end - timedelta(seconds=1))
            ], "3", "0", "3", 3.0, 2),
            ("empty meters", [], "0", "0", "0", 0.0, 0),
            ("solar export", [("SOLAR", 5, 50, start)], "0", "5", "-5", 0.0, 1),
            ("negative load power", [
                ("HVAC", 1, -5, start), ("HVAC", 1, -2, start)
            ], "2", "0", "2", -2.0, 2)
        ]
        for name, readings, load, solar, net, peak, count in cases:
            with self.subTest(scenario=name):
                building = Building(1, "Campus", "Dortmund", 2500, "University")
                meters = {}
                for meter_id, category in enumerate(["HVAC", "LIGHTING", "PLUG", "SOLAR"], 1):
                    meters[category] = Meter(meter_id, category, "kWh")
                    building.add_meter(meters[category])
                for reading_id, (category, energy, power, timestamp) in enumerate(readings, 1):
                    meters[category].add_reading(
                        EnergyReading(reading_id, timestamp, energy, power, "MANUAL")
                    )
                before = [reading.to_dict() for meter in building.meters for reading in meter.readings]
                stored_meters = building.meters.copy()
                stored_readings = [meter.readings.copy() for meter in building.meters]
                summary = service.summarize(building, start, end)
                self.assertIsInstance(summary, ConsumptionSummary)
                self.assertEqual(summary.building_id, building.id)
                self.assertEqual(summary.gross_load_kwh, Decimal(load))
                self.assertEqual(summary.solar_generation_kwh, Decimal(solar))
                self.assertEqual(summary.net_grid_kwh, Decimal(net))
                self.assertEqual(summary.peak_kw, peak)
                self.assertEqual(summary.reading_count, count)
                self.assertEqual(building.meters, stored_meters)
                self.assertEqual([meter.readings for meter in building.meters], stored_readings)
                self.assertEqual(
                    [reading.to_dict() for meter in building.meters for reading in meter.readings], before
                )
                if name == "all categories":
                    self.assertEqual(summary.category_totals_kwh, {
                        "HVAC": Decimal("120"), "LIGHTING": Decimal("30"), "PLUG": Decimal("30")
                    })

        building = Building(2, "Lab", "Dortmund", 100, "Research")
        empty = service.summarize(building, start, end)
        self.assertEqual(empty.gross_load_kwh, Decimal("0"))
        self.assertEqual(empty.solar_generation_kwh, Decimal("0"))
        self.assertEqual(empty.net_grid_kwh, Decimal("0"))
        self.assertEqual(empty.peak_kw, 0.0)
        self.assertEqual(empty.reading_count, 0)

        # Exercise event ingestion, batch ingestion and analytics together.
        load_meter = Meter(1, "HVAC", "kWh")
        solar_meter = Meter(2, "SOLAR", "kWh")
        inactive = Meter(3, "LIGHTING", "kWh", False)
        for meter in [load_meter, solar_meter, inactive]:
            building.add_meter(meter)
        ingestion = ReadingIngestionService(ReadingValidator())
        event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "consumption_kwh": 0.1, "power_kw": 4.5, "timestamp": start.isoformat()
        }
        ingestion.ingest_event(load_meter, event, 1)
        second = EnergyReading(2, start + timedelta(hours=1), "0.2", 3, "MANUAL")
        ingestion.ingest_batch(load_meter, [second])
        solar_meter.add_reading(EnergyReading(3, start, "0.05", 99, "MANUAL"))
        for field, value in [
            ("is_valid", False), ("timestamp", start.replace(tzinfo=None)),
            ("timestamp", start.astimezone(timezone(timedelta(hours=2)))),
            ("consumption_kwh", Decimal("NaN"))
        ]:
            reading = EnergyReading(4, start, 50, 50, "MANUAL")
            setattr(reading, field, value)
            load_meter.add_reading(reading)
        inactive.add_reading(EnergyReading(5, start, 100, 100, "MANUAL"))
        summary = service.summarize(building, start, end)
        self.assertEqual(summary.gross_load_kwh, Decimal("0.3"))
        self.assertEqual(summary.solar_generation_kwh, Decimal("0.05"))
        self.assertEqual(summary.net_grid_kwh, Decimal("0.25"))
        self.assertIsInstance(summary.net_grid_kwh, Decimal)
        self.assertEqual(summary.peak_kw, 4.5)
        self.assertEqual(summary.reading_count, 3)
        self.assertEqual(summary.category_totals_kwh, {
            "HVAC": Decimal("0.3"), "LIGHTING": Decimal("0"), "PLUG": Decimal("0")
        })

        with self.assertRaises(TypeError):
            service.summarize(None, start, end)
        for invalid_start, invalid_end, expected_error in [
            (start, start, ValueError), (end, start, ValueError),
            (start.replace(tzinfo=None), end, ValueError),
            (start, end.replace(tzinfo=None), ValueError),
            (start, end.astimezone(timezone(timedelta(hours=1))), ValueError),
            (None, end, TypeError)
        ]:
            with self.subTest(start=invalid_start, end=invalid_end):
                with self.assertRaises(expected_error):
                    service.summarize(building, invalid_start, invalid_end)


if __name__ == "__main__":
    unittest.main()
