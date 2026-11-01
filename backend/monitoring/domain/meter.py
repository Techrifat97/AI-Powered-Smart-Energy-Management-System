
from .energy_reading import EnergyReading


class Meter:
    def __init__(self, meter_id, category, unit, is_active=True):
        self.id = meter_id
        self.set_category(category)
        self.unit = unit
        self.set_status(is_active)
        self.readings = []

    def get_id(self):
        return self.id

    def get_category(self):
        return self.category

    def get_unit(self):
        return self.unit

    def get_status(self):
        return self.is_active

    def set_category(self, new_category):
        if new_category not in ["HVAC", "LIGHTING", "PLUG", "SOLAR"]:
            raise ValueError("Invalid meter category")
        self.category = new_category

    def set_unit(self, new_unit):
        self.unit = new_unit

    def set_status(self, status):
        if not isinstance(status, bool):
            raise ValueError("Meter status must be True or False")
        self.is_active = status

    def add_reading(self, reading):
        if not isinstance(reading, EnergyReading):
            raise TypeError("Expected an EnergyReading object")
        self.readings.append(reading)

    def latest_reading(self):
        if not self.readings:
            return None

        latest = self.readings[0]
        for reading in self.readings:
            if reading.timestamp > latest.timestamp:
                latest = reading
        return latest
