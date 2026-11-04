"""Small, reusable processing stages for dictionary-based energy events."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal


def _nonnegative_number(value, name):
    """Use Decimal for comparisons and signed energy calculations."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError(name + " must be a number")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError(name + " must be finite and nonnegative")
    return number


def _validate_event(event):
    """Check the shared event format before a processor uses it."""
    if not isinstance(event, dict):
        raise TypeError("Event must be a dictionary")
    for field in ["meter_id", "category", "is_active", "power_kw", "consumption_kwh", "timestamp"]:
        if field not in event:
            raise ValueError("Missing event field: " + field)
    if isinstance(event["meter_id"], bool) or not isinstance(event["meter_id"], int):
        raise TypeError("Meter ID must be an integer")
    if event["meter_id"] <= 0:
        raise ValueError("Meter ID must be positive")
    if event["category"] not in ["HVAC", "LIGHTING", "PLUG", "SOLAR", "BATTERY"]:
        raise ValueError("Unsupported meter category")
    if not isinstance(event["is_active"], bool):
        raise TypeError("Meter activity must be True or False")
    power = _nonnegative_number(event["power_kw"], "Power")
    energy = _nonnegative_number(event["consumption_kwh"], "Energy")

    if not isinstance(event["timestamp"], str):
        raise TypeError("Timestamp must be an ISO datetime string")
    timestamp_text = event["timestamp"]
    if timestamp_text.endswith("Z"):
        timestamp_text = timestamp_text[:-1] + "+00:00"
    try:
        timestamp = datetime.fromisoformat(timestamp_text)
    except ValueError:
        raise ValueError("Timestamp must be an ISO datetime string") from None
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError("Timestamp must be timezone-aware UTC")
    if event["category"] == "BATTERY":
        if event.get("battery_mode") not in ["CHARGING", "DISCHARGING"]:
            raise ValueError("Battery mode must be CHARGING or DISCHARGING")

    # Older six-field events can still be processed without duration metadata.
    if "measurement_seconds" in event:
        seconds = _nonnegative_number(event["measurement_seconds"], "Measurement duration")
        if seconds == 0:
            raise ValueError("Measurement duration must be positive")
        expected_energy = power * seconds / Decimal("3600")
        # Allow only tiny differences caused by converting energy to a float.
        if abs(energy - expected_energy) > Decimal("0.000000001"):
            raise ValueError("Energy does not match power and measurement duration")


class StreamProcessor(ABC):
    """A processor returns an event dictionary, or None to reject it."""

    @abstractmethod
    def process(self, event):
        """Process one event."""
        raise NotImplementedError

    def __or__(self, other):
        """Connect this processor to another processor or pipeline."""
        if isinstance(other, StreamPipeline):
            return StreamPipeline([self] + other.processors)
        return StreamPipeline([self, other])


class MeterFilter(StreamProcessor):
    """Keep active readings at or above the minimum power, for every category."""

    def __init__(self, min_power_kw=0.5):
        self.min_power_kw = _nonnegative_number(min_power_kw, "Minimum power")

    def process(self, event):
        _validate_event(event)
        if not event["is_active"]:
            return None
        if Decimal(str(event["power_kw"])) < self.min_power_kw:
            return None
        return event


class EnergyTransformer(StreamProcessor):
    """Add this event's signed energy contribution, not a whole-building total."""

    def process(self, event):
        _validate_event(event)
        contribution = Decimal(str(event["consumption_kwh"]))
        if event["category"] == "SOLAR":
            contribution = -contribution
        elif event["category"] == "BATTERY" and event["battery_mode"] == "DISCHARGING":
            contribution = -contribution
        result = event.copy()
        result["net_grid_contribution_kwh"] = contribution
        return result


class PeakTariffProcessor(StreamProcessor):
    """Flag consumption strictly above a power threshold; no billing is performed."""

    def __init__(self, threshold_kw=4.0):
        self.threshold_kw = _nonnegative_number(threshold_kw, "Peak threshold")

    def process(self, event):
        _validate_event(event)
        consumption = event["category"] in ["HVAC", "LIGHTING", "PLUG"]
        if event["category"] == "BATTERY" and event["battery_mode"] == "CHARGING":
            consumption = True
        result = event.copy()
        result["is_peak"] = consumption and Decimal(str(event["power_kw"])) > self.threshold_kw
        return result


class StreamPipeline:
    """Run the same processor interface in order, one event at a time."""

    def __init__(self, processors):
        self.processors = list(processors)
        for processor in self.processors:
            if not isinstance(processor, StreamProcessor):
                raise TypeError("Each stage must be a StreamProcessor")

    def __or__(self, other):
        """Build a new pipeline without changing the original pipeline."""
        if isinstance(other, StreamPipeline):
            return StreamPipeline(self.processors + other.processors)
        return StreamPipeline(self.processors + [other])

    def run(self, events):
        """Yield accepted results without collecting the input stream."""
        for event in events:
            result = event
            for processor in self.processors:
                result = processor.process(result)
                if result is None:
                    break
                if not isinstance(result, dict):
                    raise TypeError("A processor must return a dictionary or None")
            if result is not None:
                yield result
