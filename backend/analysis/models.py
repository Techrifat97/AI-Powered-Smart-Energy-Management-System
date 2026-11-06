from django.db import models


class TariffPlan(models.Model):
    """
    Subsystem 3 (Analysis / Marwan): Electricity pricing structures and time-of-use tariffs.
    """
    name = models.CharField(max_length=100)
    rate_standard_eur_per_kwh = models.FloatField(default=0.32, help_text="Off-peak / standard rate in €/kWh")
    rate_peak_eur_per_kwh = models.FloatField(default=0.45, help_text="Peak demand rate in €/kWh")
    peak_start_hour = models.IntegerField(default=11, help_text="Peak rate starting hour (0-23)")
    peak_end_hour = models.IntegerField(default=16, help_text="Peak rate ending hour (0-23)")
    solar_feed_in_eur_per_kwh = models.FloatField(default=0.08, help_text="Solar feed-in credit in €/kWh")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.name} (€{self.rate_standard_eur_per_kwh}/kWh)"


class EnergyAlert(models.Model):
    """
    Subsystem 3 (Analysis / Marwan): Threshold violations, anomaly alerts, and spikes.
    """
    SEVERITY_CHOICES = [
        ('CRITICAL', 'Critical'),
        ('WARNING', 'Warning'),
        ('INFO', 'Informational'),
    ]

    ALERT_TYPES = [
        ('PEAK_SPIKE', 'Peak Demand Spike'),
        ('UNUSUAL_NIGHT_LOAD', 'Unusual Nighttime Load'),
        ('BUDGET_EXCEEDED', 'Budget Limit Exceeded'),
        ('METER_OFFLINE', 'Smart Meter Communication Failure'),
    ]

    building = models.ForeignKey(
        'monitoring.Building',
        related_name='alerts',
        on_delete=models.CASCADE
    )
    meter = models.ForeignKey(
        'monitoring.Meter',
        related_name='alerts',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='WARNING')
    alert_type = models.CharField(max_length=40, choices=ALERT_TYPES, default='PEAK_SPIKE')
    message = models.TextField()
    value_recorded = models.FloatField(default=0.0, help_text="Observed anomalous reading value")
    threshold_value = models.FloatField(default=0.0, help_text="Threshold limit that was exceeded")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.get_alert_type_display()} - {self.building.name}"


class CostReport(models.Model):
    """
    Subsystem 3 (Analysis / Marwan): Monthly aggregated financial expenditure breakdown.
    """
    building = models.ForeignKey(
        'monitoring.Building',
        related_name='cost_reports',
        on_delete=models.CASCADE
    )
    tariff = models.ForeignKey(
        TariffPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_grid_kwh = models.FloatField(default=0.0)
    total_cost_eur = models.FloatField(default=0.0)
    solar_savings_eur = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end']

    def __str__(self):
        return f"Cost Report: {self.building.name} ({self.period_start} to {self.period_end}): €{self.total_cost_eur:.2f}"

