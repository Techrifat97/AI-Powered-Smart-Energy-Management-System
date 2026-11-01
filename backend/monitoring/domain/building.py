from datetime import datetime

class Building:
    def __init__(self, building_ID, name, address, floor_area_m2, building_type):
        self.id = building_ID
        self.name = name
        self.address = address
        self.floor_area_m2 = floor_area_m2
        self.building_type = building_type
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
        self.meters.append(meter)

    def active_meters(self):
        active_list = []
        for meter in self.meters:
            if meter.is_active:
                active_list.append(meter)
                         
        return active_list