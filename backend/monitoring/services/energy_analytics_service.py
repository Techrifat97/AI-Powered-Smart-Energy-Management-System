"""Summarize accepted readings without changing the original data."""

from decimal import Decimal

from ..domain.building import Building
from ..domain.consumption_summary import ConsumptionSummary
from ..domain.validation import validate_utc_timestamp
from .reading_validator import ReadingValidator
from ..errors import InvalidSummaryError, MonitoringTypeError


class EnergyAnalyticsService:
    """Aggregate load and solar energy over a UTC interval [start, end)."""

    def summarize(self, building: Building, start, end) -> ConsumptionSummary:
        """Peak is the maximum individual load reading, not a building-wide peak."""
        if not isinstance(building, Building):
            raise MonitoringTypeError("Expected a Building object")
        validate_utc_timestamp(start, "Start")
        validate_utc_timestamp(end, "End")
        if start >= end:
            raise InvalidSummaryError("Start must be before end")

        category_totals = {
            "HVAC": Decimal("0"), "LIGHTING": Decimal("0"), "PLUG": Decimal("0")
        }
        solar_generation = Decimal("0")
        peak = None
        reading_count = 0
        validator = ReadingValidator()

        for meter in building.active_meters():
            if meter.category not in ["HVAC", "LIGHTING", "PLUG", "SOLAR"]:
                continue
            for reading in meter.readings:
                # Older code can add readings directly, so check them again.
                try:
                    validator.validate(meter, reading)
                except (TypeError, ValueError):
                    continue
                if not start <= reading.timestamp < end:
                    continue

                if meter.category == "SOLAR":
                    solar_generation += reading.consumption_kwh
                else:
                    category_totals[meter.category] += reading.consumption_kwh
                    if peak is None or reading.power_kw > peak:
                        peak = reading.power_kw
                reading_count += 1

        gross_load = Decimal("0")
        for total in category_totals.values():
            gross_load += total
        if peak is None:
            peak = 0.0

        return ConsumptionSummary(
            building_id=building.id,
            start=start,
            end=end,
            gross_load_kwh=gross_load,
            solar_generation_kwh=solar_generation,
            net_grid_kwh=gross_load - solar_generation,
            category_totals_kwh=category_totals,
            peak_kw=peak,
            reading_count=reading_count
        )
