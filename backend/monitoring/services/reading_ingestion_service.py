"""Accept validated readings into the existing in-memory Meter objects."""

from datetime import datetime

from ..domain.energy_reading import EnergyReading
from ..domain.meter import Meter
from ..domain.validation import to_decimal
from .reading_validator import ReadingValidator
from ..errors import InvalidEventError, MonitoringTypeError


class ReadingIngestionService:
    """Validate first, then store readings through Meter.add_reading()."""

    def __init__(self, validator: ReadingValidator):
        if not isinstance(validator, ReadingValidator):
            raise MonitoringTypeError("Expected a ReadingValidator object")
        self.validator = validator

    def ingest(self, meter: Meter, reading: EnergyReading) -> EnergyReading:
        """Store one accepted reading and return the same object."""
        self.validator.validate(meter, reading)
        meter.add_reading(reading)
        return reading

    def ingest_batch(self, meter: Meter, readings) -> list[EnergyReading]:
        """Validate the entire batch before adding any readings to one meter."""
        if not isinstance(meter, Meter):
            raise MonitoringTypeError("Expected a Meter object")
        batch = list(readings)
        for reading in batch:
            self.validator.validate(meter, reading)
        for reading in batch:
            meter.add_reading(reading)
        return batch

    def ingest_event(self, meter: Meter, event_dict: dict, reading_id) -> EnergyReading:
        """Adapt a Hometask 2 event; no streaming import is needed."""
        if not isinstance(meter, Meter):
            raise MonitoringTypeError("Expected a Meter object")
        if not isinstance(event_dict, dict):
            raise MonitoringTypeError("Event must be a dictionary")
        required_fields = [
            "meter_id", "category", "is_active", "power_kw",
            "consumption_kwh", "timestamp"
        ]
        for field in required_fields:
            if field not in event_dict:
                raise InvalidEventError("Missing event field: " + field)

        meter_id = event_dict["meter_id"]
        if isinstance(meter_id, bool) or not isinstance(meter_id, int):
            raise MonitoringTypeError("Event meter ID must be an integer")
        if meter_id != meter.id:
            raise InvalidEventError("Event meter ID does not match the destination meter")
        if event_dict["category"] != meter.category:
            raise InvalidEventError("Event category does not match the destination meter")
        if not isinstance(event_dict["is_active"], bool):
            raise MonitoringTypeError("Event activity must be a Boolean")
        if event_dict["is_active"] != meter.is_active:
            raise InvalidEventError("Event activity does not match the destination meter")

        timestamp_text = event_dict["timestamp"]
        if not isinstance(timestamp_text, str):
            raise MonitoringTypeError("Event timestamp must be an ISO datetime string")
        if timestamp_text.endswith("Z"):
            timestamp_text = timestamp_text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(timestamp_text)
        except ValueError:
            raise InvalidEventError("Event timestamp must be an ISO datetime string") from None

        consumption = to_decimal(event_dict["consumption_kwh"], "Consumption")
        if isinstance(event_dict["power_kw"], bool):
            raise MonitoringTypeError("Power must be a number")
        reading = EnergyReading(
            reading_id, timestamp, consumption, event_dict["power_kw"], "SIMULATED"
        )
        return self.ingest(meter, reading)
