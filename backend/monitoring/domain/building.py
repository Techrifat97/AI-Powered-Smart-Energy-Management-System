from datetime import datetime

class Building:
    def __init__(self, building_ID, name, address, floor_area_m2, building_type):
        self.id = building_ID
        self.name = name
        self.address = address
        self.floor_area_m2 = floor_area_m2
        self.building_type = building_type
        self.created_at = datetime.now()
        
    def get_name(self):
        return self.name

    def get_address(self):
        return self.address

    def set_name(self, new_name):
        self.name = new_name
    
    def set_address(self, new_address):
        self.address = new_address

building1 = Building(1, "FH Dortmund", "Dortmund", 2500.0, "University")

print(building1.get_name())
print(building1.get_address())

building1.set_name('Smart Energy Building')

print(building1.get_name())