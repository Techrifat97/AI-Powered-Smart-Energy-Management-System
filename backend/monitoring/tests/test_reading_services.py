import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from backend.monitoring.domain.energy_reading import EnergyReading
from backend.monitoring.domain.meter import Meter
from backend.monitoring.services.reading_ingestion_service import ReadingIngestionService
from backend.monitoring.services.reading_validator import ReadingValidator


class ReadingValidatorTests(unittest.TestCase):
    def setUp(self):
        self.meter = Meter(1, "HVAC", "kWh")
        self.timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.reading = EnergyReading(1, self.timestamp, "1.25", 2.5, "MANUAL")
        self.validator = ReadingValidator()

    def test_valid_reading_does_not_change_objects(self):
        before = self.reading.to_dict()
        self.assertIsNone(self.validator.validate(self.meter, self.reading))
        self.assertEqual(self.reading.to_dict(), before)
        self.assertEqual(self.meter.readings, [])
        self.assertTrue(self.meter.is_active)

    def test_wrong_object_types(self):
        for meter, reading in [(None, self.reading), (self.meter, {}), (1, None)]:
            with self.subTest(meter=meter, reading=reading):
                with self.assertRaises(TypeError):
                    self.validator.validate(meter, reading)

    def test_inactive_meter_and_invalid_reading(self):
        self.meter.set_status(False)
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.validator.validate(self.meter, self.reading)
        self.meter.set_status(True)
        self.reading.is_valid = False
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.validator.validate(self.meter, self.reading)

    def test_mutated_flags_must_still_be_boolean(self):
        for status in ["False", 0, None]:
            with self.subTest(status=status):
                self.meter.is_active = status
                with self.assertRaises(TypeError):
                    self.validator.validate(self.meter, self.reading)
                self.meter.is_active = True
                self.reading.is_valid = status
                with self.assertRaises(TypeError):
                    self.validator.validate(self.meter, self.reading)
                self.reading.is_valid = True

    def test_invalid_measurements(self):
        cases = [
            ("consumption_kwh", Decimal("-1"), ValueError),
            ("consumption_kwh", Decimal("NaN"), ValueError),
            ("consumption_kwh", Decimal("Infinity"), ValueError),
            ("consumption_kwh", 1.25, TypeError),
            ("consumption_kwh", None, TypeError),
            ("power_kw", float("nan"), ValueError),
            ("power_kw", float("inf"), ValueError),
            ("power_kw", "2.5", TypeError),
            ("power_kw", True, TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                reading = EnergyReading(2, self.timestamp, 1, 2, "MANUAL")
                setattr(reading, field, value)
                with self.assertRaises(expected_error):
                    self.validator.validate(self.meter, reading)

    def test_timestamp_rules_and_naive_constructor_compatibility(self):
        naive = datetime(2026, 1, 1, 12)
        reading = EnergyReading(2, naive, 1, 2, "MANUAL")
        self.assertEqual(reading.timestamp, naive)
        cases = [
            (naive, ValueError),
            (self.timestamp.astimezone(timezone(timedelta(hours=2))), ValueError),
            ("2026-01-01", TypeError),
            (None, TypeError)
        ]
        for timestamp, expected_error in cases:
            with self.subTest(timestamp=timestamp):
                reading.timestamp = timestamp
                with self.assertRaises(expected_error):
                    self.validator.validate(self.meter, reading)

    def test_zero_consumption_and_finite_negative_power(self):
        reading = EnergyReading(2, self.timestamp, 0, -2, "SIMULATED")
        self.validator.validate(self.meter, reading)
        self.assertEqual(reading.consumption_kwh, Decimal("0"))
        self.assertEqual(reading.power_kw, -2.0)


class ReadingIngestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.meter = Meter(1, "HVAC", "kWh")
        self.timestamp = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.validator = ReadingValidator()
        self.service = ReadingIngestionService(self.validator)
        self.reading = EnergyReading(1, self.timestamp, "0.1", 2, "MANUAL")
        self.event = {
            "meter_id": 1, "category": "HVAC", "is_active": True,
            "consumption_kwh": 0.1, "power_kw": 2.5,
            "timestamp": "2026-01-01T12:00:00+00:00"
        }

    def test_single_ingestion_uses_validator_and_meter(self):
        with patch.object(self.validator, "validate", wraps=self.validator.validate) as validate:
            with patch.object(self.meter, "add_reading", wraps=self.meter.add_reading) as add:
                accepted = self.service.ingest(self.meter, self.reading)
                validate.assert_called_once_with(self.meter, self.reading)
                add.assert_called_once_with(self.reading)
        self.assertIs(accepted, self.reading)
        self.assertEqual(self.meter.readings, [self.reading])

    def test_invalid_single_reading_is_not_stored(self):
        self.reading.is_valid = False
        with self.assertRaises(ValueError):
            self.service.ingest(self.meter, self.reading)
        self.assertEqual(self.meter.readings, [])

    def test_batch_ingestion_accepts_an_iterator_and_empty_batch(self):
        second = EnergyReading(2, self.timestamp, "0.2", 3, "SIMULATED")
        readings = [self.reading, second]
        accepted = self.service.ingest_batch(self.meter, iter(readings))
        self.assertEqual(accepted, readings)
        self.assertEqual(self.meter.readings, readings)
        self.assertEqual(self.service.ingest_batch(self.meter, []), [])
        self.assertEqual(self.meter.readings, readings)

    def test_failed_batch_keeps_existing_readings_without_partial_writes(self):
        self.service.ingest(self.meter, self.reading)
        valid = EnergyReading(2, self.timestamp, 1, 2, "MANUAL")
        invalid = EnergyReading(3, self.timestamp, 1, 2, "MANUAL", False)
        for bad_reading, expected_error in [(invalid, ValueError), ({}, TypeError)]:
            with self.subTest(bad_reading=bad_reading):
                with self.assertRaises(expected_error):
                    self.service.ingest_batch(self.meter, iter([valid, bad_reading]))
                self.assertEqual(self.meter.readings, [self.reading])

    def test_batch_iterator_failure_does_not_store_anything(self):
        def broken_batch():
            yield self.reading
            raise ValueError("Input stream failed")

        with self.assertRaisesRegex(ValueError, "Input stream failed"):
            self.service.ingest_batch(self.meter, broken_batch())
        self.assertEqual(self.meter.readings, [])

    def test_invalid_service_inputs(self):
        with self.assertRaises(TypeError):
            ReadingIngestionService(None)
        with self.assertRaises(TypeError):
            self.service.ingest_batch(None, [])
        with self.assertRaises(TypeError):
            self.service.ingest_batch(self.meter, None)

    def test_event_adapter_accepts_iso_utc_and_z_without_changing_event(self):
        for timestamp in ["2026-01-01T12:00:00+00:00", "2026-01-01T12:00:00Z"]:
            with self.subTest(timestamp=timestamp):
                event = self.event.copy()
                event["timestamp"] = timestamp
                before = event.copy()
                reading = self.service.ingest_event(self.meter, event, 10)
                self.assertEqual(reading.id, 10)
                self.assertEqual(reading.timestamp, self.timestamp)
                self.assertEqual(reading.consumption_kwh, Decimal("0.1"))
                self.assertEqual(reading.source, "SIMULATED")
                self.assertIs(self.meter.readings[-1], reading)
                self.assertEqual(event, before)

    def test_event_adapter_rejects_missing_fields_and_wrong_types(self):
        with self.assertRaises(TypeError):
            self.service.ingest_event(self.meter, [], 1)
        with self.assertRaises(TypeError):
            self.service.ingest_event(None, self.event, 1)
        for field in self.event:
            with self.subTest(field=field):
                event = self.event.copy()
                del event[field]
                with self.assertRaises(ValueError):
                    self.service.ingest_event(self.meter, event, 1)
        self.assertEqual(self.meter.readings, [])

    def test_event_adapter_rejects_mismatches_and_invalid_values(self):
        cases = [
            ("meter_id", 99, ValueError),
            ("meter_id", True, TypeError),
            ("category", "SOLAR", ValueError),
            ("is_active", False, ValueError),
            ("is_active", "False", TypeError),
            ("timestamp", "not a timestamp", ValueError),
            ("timestamp", "2026-01-01T12:00:00", ValueError),
            ("timestamp", "2026-01-01T12:00:00+02:00", ValueError),
            ("timestamp", self.timestamp, TypeError),
            ("consumption_kwh", -1, ValueError),
            ("consumption_kwh", "NaN", ValueError),
            ("consumption_kwh", "invalid", ValueError),
            ("consumption_kwh", True, TypeError),
            ("consumption_kwh", None, TypeError),
            ("power_kw", float("inf"), ValueError),
            ("power_kw", True, TypeError)
        ]
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                event = self.event.copy()
                event[field] = value
                with self.assertRaises(expected_error):
                    self.service.ingest_event(self.meter, event, 1)
                self.assertEqual(self.meter.readings, [])

    def test_event_adapter_rejects_inactive_destination(self):
        self.meter.set_status(False)
        self.event["is_active"] = False
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.service.ingest_event(self.meter, self.event, 1)
        self.assertEqual(self.meter.readings, [])


if __name__ == "__main__":
    unittest.main()
