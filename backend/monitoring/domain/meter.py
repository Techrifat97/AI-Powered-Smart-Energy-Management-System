
class Meter:
    def __init__(self, meter_id, category, unit, is_active=True):
        self.id = meter_id
        self.category = category
        self.unit = unit
        self.is_active = is_active
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
        self.is_active = status

    def add_reading(self, reading):
        self.readings.append(reading)

    def latest_reading(self):
        if not self.readings:
            return None

        return max(self.readings, key=lambda reading: reading.timestamp)


meter1 = Meter(1, "HVAC", "kWh")

print(meter1.get_category())
print(meter1.get_status())

meter1.set_status(False)
print(meter1.get_status())