from django.db import models


class Building(models.Model):
    """
    Subsystem 1 (Monitoring): Core physical entity tracked by the energy management system.
    """
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, blank=True, default='')
    area_sqm = models.FloatField(default=1000.0, help_text="Total floor area in square meters")
    baseline_kwh_per_day = models.FloatField(
        default=250.0,
        help_text="Target or historical baseline daily consumption in kWh"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name} (ID: {self.id})"


class Meter(models.Model):
    """
    Subsystem 1 (Monitoring): Smart metering hardware device mapped to a building.
    """
    METER_TYPES = [
        ('ELECTRICITY', 'Electricity Main'),
        ('SOLAR', 'Solar PV Generation'),
        ('HVAC', 'HVAC System'),
        ('LIGHTING', 'Lighting Circuit'),
    ]

    building = models.ForeignKey(Building, related_name='meters', on_delete=models.CASCADE)
    device_id = models.CharField(max_length=64, unique=True)
    meter_type = models.CharField(max_length=32, choices=METER_TYPES, default='ELECTRICITY')
    unit = models.CharField(max_length=16, default='kWh')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.device_id} ({self.get_meter_type_display()}) - {self.building.name}"


class EnergyReading(models.Model):
    """
    Subsystem 1 (Monitoring): Time-series telemetry readings recorded by a meter.
    """
    meter = models.ForeignKey(Meter, related_name='readings', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(db_index=True)
    energy_kwh = models.FloatField(help_text="Energy consumption in kWh for this interval")
    power_kw = models.FloatField(default=0.0, help_text="Instantaneous power demand in kW")
    voltage = models.FloatField(default=230.0, help_text="Grid voltage in Volts")

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['meter', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.meter.device_id} @ {self.timestamp}: {self.energy_kwh:.2f} kWh"
