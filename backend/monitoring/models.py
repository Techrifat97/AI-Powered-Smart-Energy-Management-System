from sys import float_info

from django.core.validators import MinValueValidator
from django.db import models

from .validators import validate_finite, validate_interval_timestamp, validate_positive


class Building(models.Model):
    """
    Subsystem 1: Building metadata and reference daily consumption.
    """
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, blank=True, default='')
    area_sqm = models.FloatField(
        default=1000.0,
        validators=[validate_positive],
        help_text="Total floor area in square meters",
    )
    baseline_kwh_per_day = models.FloatField(
        default=250.0,
        validators=[validate_finite, MinValueValidator(0.0)],
        help_text="Target or historical baseline daily consumption in kWh"
    )
    has_solar_installation = models.BooleanField(
        null=True, blank=True, default=None,
        help_text="True: installed; False: confirmed absent for the reported history; null: unknown",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(area_sqm__gt=0.0, area_sqm__lte=float_info.max),
                name='s1_building_area_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    baseline_kwh_per_day__gte=0.0,
                    baseline_kwh_per_day__lte=float_info.max,
                ),
                name='s1_building_baseline_valid',
            ),
        ]

    def __str__(self):
        return f"{self.name} (ID: {self.id})"


class Meter(models.Model):
    """
    Smart meter mapped to a building. ELECTRICITY measures gross building load;
    HVAC and LIGHTING are included submeters, and SOLAR measures generation.
    is_active controls telemetry eligibility; deactivation retains history.
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
    unit = models.CharField(max_length=16, default='kWh', choices=[('kWh', 'kWh')])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(meter_type__in=['ELECTRICITY', 'SOLAR', 'HVAC', 'LIGHTING']),
                name='s1_meter_type_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(unit='kWh'),
                name='s1_meter_unit_kwh',
            ),
        ]

    def __str__(self):
        return f"{self.device_id} ({self.get_meter_type_display()}) - {self.building.name}"


class EnergyReading(models.Model):
    """
    Energy measured during an interval, not a cumulative lifetime counter.

    Simulated telemetry uses 60-second intervals starting on UTC minute boundaries.
    Existing hourly demo readings keep their original energy and timestamps.
    A power sample need not equal average interval power, so no energy/power
    equality is imposed. Solar direction is represented by meter_type; stored
    energy and power are nonnegative magnitudes.

    New input requires full_clean() validation. As with normal Django models,
    save()/bulk_create() do not call field validators automatically. Numeric,
    meter-type/unit and uniqueness constraints also protect direct database writes;
    timestamp alignment is model validation, not a database constraint.
    """
    meter = models.ForeignKey(Meter, related_name='readings', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(
        db_index=True,
        validators=[validate_interval_timestamp],
        help_text="Interval start: timezone-aware UTC, aligned to a minute",
    )
    interval_seconds = models.PositiveIntegerField(
        null=True, blank=True, default=None, validators=[MinValueValidator(1)],
        help_text="Duration from timestamp (inclusive); null means unknown, never inferred",
    )
    energy_kwh = models.FloatField(
        validators=[validate_finite, MinValueValidator(0.0)],
        help_text="Energy consumed or generated in kWh during this interval, not cumulative",
    )
    power_kw = models.FloatField(
        default=0.0,
        validators=[validate_finite, MinValueValidator(0.0)],
        help_text="Instantaneous consumption or generation power in kW (nonnegative)",
    )
    voltage = models.FloatField(
        default=230.0,
        validators=[validate_finite, MinValueValidator(0.0)],
        help_text="Grid voltage in Volts (zero is allowed for an unpowered circuit)",
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['meter', 'timestamp']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(interval_seconds__isnull=True) | models.Q(interval_seconds__gt=0),
                name='s1_reading_duration_positive',
            ),
            # The largest finite float excludes PostgreSQL NaN and infinities.
            models.CheckConstraint(
                condition=models.Q(energy_kwh__gte=0.0, energy_kwh__lte=float_info.max),
                name='s1_reading_energy_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(power_kw__gte=0.0, power_kw__lte=float_info.max),
                name='s1_reading_power_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(voltage__gte=0.0, voltage__lte=float_info.max),
                name='s1_reading_voltage_valid',
            ),
            models.UniqueConstraint(
                fields=['meter', 'timestamp'], name='s1_reading_meter_timestamp_unique',
            ),
        ]

    def __str__(self):
        return f"{self.meter.device_id} @ {self.timestamp}: {self.energy_kwh:.2f} kWh"
