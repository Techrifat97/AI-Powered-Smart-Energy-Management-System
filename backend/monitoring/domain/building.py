from datetime import datetime
from math import isfinite
from .meter import Meter


class Building:
    def __init__(self, building_ID, name, address, floor_area_m2, building_type):
        if not isinstance(building_type, str) or not building_type.strip():
            raise ValueError("Building type cannot be empty")
        floor_area = float(floor_area_m2)
        if not isfinite(floor_area) or floor_area <= 0:
            raise ValueError("Floor area must be positive")

        self.id = building_ID
        self.name = name
        self.address = address
        self.floor_area_m2 = floor_area
        self.type = building_type
        self.created_at = datetime.now()
        self.meters = []

    def get_name(self):
        return self.name

    def get_address(self):
        return self.address

    def set_name(self, new_name):
        self.name = new_name

    def set_address(self, new_address):
        self.address = new_address

    def add_meter(self, meter):
        if not isinstance(meter, Meter):
            raise TypeError("Expected a Meter object")
        self.meters.append(meter)

    def active_meters(self):
        active_list = []
        for meter in self.meters:
            if meter.is_active:
                active_list.append(meter)

        return active_list