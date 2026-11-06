"""Aggregated energy data returned by EnergyAnalyticsService."""

from decimal import Decimal
from math import isfinite

from .validation import to_decimal, validate_utc_timestamp
from ..errors import InvalidSummaryError, MonitoringTypeError


class ConsumptionSummary:
    """Keep load consumption separate from solar generation."""

    def __init__(self, building_id, start, end, gross_load_kwh,
                 solar_generation_kwh, net_grid_kwh, category_totals_kwh,
                 peak_kw, reading_count):
        if isinstance(building_id, bool) or not isinstance(building_id, int):
            raise MonitoringTypeError("Building ID must be an integer")
        validate_utc_timestamp(start, "Start")
        validate_utc_timestamp(end, "End")
        if start >= end:
            raise InvalidSummaryError("Start must be before end")
        if not isinstance(category_totals_kwh, dict):
            raise MonitoringTypeError("Category totals must be a dictionary")
        if isinstance(reading_count, bool) or not isinstance(reading_count, int):
            raise MonitoringTypeError("Reading count must be an integer")
        if reading_count < 0:
            raise InvalidSummaryError("Reading count cannot be negative")
        if isinstance(peak_kw, bool) or not isinstance(peak_kw, (int, float)):
            raise MonitoringTypeError("Peak power must be a number")
        if not isfinite(peak_kw):
            raise InvalidSummaryError("Peak power must be finite")

        self.building_id = building_id
        self.start = start
        self.end = end
        self.gross_load_kwh = to_decimal(gross_load_kwh, "Gross load")
        self.solar_generation_kwh = to_decimal(solar_generation_kwh, "Solar generation")
        self.net_grid_kwh = to_decimal(net_grid_kwh, "Net grid energy", allow_negative=True)
        self.category_totals_kwh = {
            "HVAC": Decimal("0"), "LIGHTING": Decimal("0"), "PLUG": Decimal("0")
        }
        for category, total in category_totals_kwh.items():
            if category not in self.category_totals_kwh:
                raise InvalidSummaryError("Category totals may contain only HVAC, LIGHTING and PLUG")
            self.category_totals_kwh[category] = to_decimal(total, "Category total")

        total_load = Decimal("0")
        for total in self.category_totals_kwh.values():
            total_load += total
        if total_load != self.gross_load_kwh:
            raise InvalidSummaryError("Category totals must equal gross load")
        if self.net_grid_kwh != self.gross_load_kwh - self.solar_generation_kwh:
            raise InvalidSummaryError("Net grid energy must equal gross load minus solar generation")
        self.peak_kw = float(peak_kw)
        self.reading_count = reading_count

    def get_building_id(self):
        return self.building_id

    def get_start(self):
        return self.start

    def get_end(self):
        return self.end

    def get_gross_load(self):
        return self.gross_load_kwh

    def get_solar_generation(self):
        return self.solar_generation_kwh

    def get_net_grid(self):
        return self.net_grid_kwh

    def get_category_totals(self):
        return self.category_totals_kwh.copy()

    def get_peak(self):
        return self.peak_kw

    def get_reading_count(self):
        return self.reading_count

    def to_dict(self):
        """Serialize Decimal energy values as strings to preserve precision."""
        category_totals = {}
        for category, total in self.category_totals_kwh.items():
            category_totals[category] = str(total)
        return {
            "building_id": self.building_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "gross_load_kwh": str(self.gross_load_kwh),
            "solar_generation_kwh": str(self.solar_generation_kwh),
            "net_grid_kwh": str(self.net_grid_kwh),
            "category_totals_kwh": category_totals,
            "peak_kw": self.peak_kw,
            "reading_count": self.reading_count
        }
