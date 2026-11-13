"""Rule-based alert detection over recorded S1 readings.

Simple, explainable thresholds, not a statistical anomaly model. Detection is
conservative: with too little data a rule stays silent. An unresolved alert of
the same type for the same building/meter is never duplicated.

Design: every rule is a subclass of the abstract `AlertRule`. An `AlertDetector`
is composed of rules and treats them polymorphically, so a new rule is one new
class and one entry in `default_rules()`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd
from django.utils import timezone

from analysis.models import EnergyAlert
from monitoring.models import EnergyReading, Meter
from monitoring.services.aggregation import building_energy_report

WINDOW = timedelta(hours=24)
MIN_SAMPLES = 10
PEAK_SPIKE_FACTOR = 2.0          # latest power vs mean power of the preceding window
NIGHT_HOURS_UTC = range(0, 5)    # 00:00-04:59 UTC
NIGHT_LOAD_FACTOR = 0.5          # night mean power vs mean power of the other hours
OFFLINE_AFTER = timedelta(minutes=15)


@dataclass(frozen=True)
class Finding:
    """What a rule reports when its condition is met."""
    severity: str
    message: str
    value: float
    threshold: float


class AlertRule(ABC):
    """A single detection rule. Subclasses implement `evaluate`."""

    alert_type: str = ''
    per_meter: bool = True       # False: evaluated once per building (meter is None)

    def applies_to(self, meter):
        return True

    @abstractmethod
    def evaluate(self, building, meter, now):
        """Return a Finding, or None when the rule is not triggered."""


class PowerSeriesRule(AlertRule, ABC):
    """Shared base for rules that analyse the last 24 h of a meter's power."""

    def applies_to(self, meter):
        return meter.meter_type == 'ELECTRICITY'

    @staticmethod
    def power_series(meter, now):
        rows = list(EnergyReading.objects.filter(
            meter=meter, timestamp__lte=now, timestamp__gt=now - WINDOW,
        ).order_by('timestamp').values_list('timestamp', 'power_kw'))
        times = [t for t, _ in rows]
        power = [p for _, p in rows]
        return pd.Series(power, index=pd.DatetimeIndex(times, tz='UTC'), dtype='float64')


class PeakSpikeRule(PowerSeriesRule):
    alert_type = 'PEAK_SPIKE'

    def evaluate(self, building, meter, now):
        series = self.power_series(meter, now)
        if len(series) <= MIN_SAMPLES:
            return None
        latest = float(series.iloc[-1])
        average = float(np.mean(series.iloc[:-1]))
        threshold = average * PEAK_SPIKE_FACTOR
        if average > 0 and latest > threshold:
            return Finding('WARNING', f'Power of {latest:.2f} kW is above {PEAK_SPIKE_FACTOR:g}x the 24 h '
                           f'average of {average:.2f} kW.', latest, threshold)
        return None


class NightLoadRule(PowerSeriesRule):
    alert_type = 'UNUSUAL_NIGHT_LOAD'

    def evaluate(self, building, meter, now):
        series = self.power_series(meter, now)
        is_night = series.index.hour.isin(list(NIGHT_HOURS_UTC))
        night, day = series[is_night], series[~is_night]
        if len(night) < MIN_SAMPLES or len(day) < MIN_SAMPLES:
            return None
        night_avg, threshold = float(np.mean(night)), float(np.mean(day)) * NIGHT_LOAD_FACTOR
        if night_avg > threshold:
            return Finding('WARNING', f'Night-time (UTC) average power of {night_avg:.2f} kW exceeds '
                           f'{NIGHT_LOAD_FACTOR:.0%} of the daytime average.', night_avg, threshold)
        return None


class MeterOfflineRule(AlertRule):
    alert_type = 'METER_OFFLINE'

    def evaluate(self, building, meter, now):
        latest = meter.readings.order_by('-timestamp').first()
        if latest is None:
            return None
        last_seen = latest.timestamp + timedelta(seconds=latest.interval_seconds or 0)
        if now - last_seen > OFFLINE_AFTER:
            minutes = (now - last_seen).total_seconds() / 60
            return Finding('CRITICAL', f'No reading from meter {meter.device_id} for {minutes:.0f} minutes.',
                           minutes, OFFLINE_AFTER.total_seconds() / 60)
        return None


class DailyBudgetRule(AlertRule):
    alert_type = 'BUDGET_EXCEEDED'
    per_meter = False

    def evaluate(self, building, meter, now):
        baseline = building.baseline_kwh_per_day
        if not baseline or baseline <= 0:
            return None
        days = building_energy_report(building)['complete_days']
        if not days:
            return None
        latest = days[-1]
        if latest['gross_kwh'] > baseline:
            return Finding('WARNING', f"Consumption of {latest['gross_kwh']:.1f} kWh on {latest['date']} "
                           f"exceeded the daily baseline of {baseline:.1f} kWh.", latest['gross_kwh'], baseline)
        return None


def default_rules():
    return [PeakSpikeRule(), NightLoadRule(), MeterOfflineRule(), DailyBudgetRule()]


class AlertDetector:
    """Runs a collection of rules over a building and stores new, non-duplicate alerts."""

    def __init__(self, rules=None):
        self.rules = list(rules) if rules is not None else default_rules()

    def _findings(self, building, now):
        for meter in Meter.objects.filter(building=building, is_active=True):
            for rule in self.rules:
                if rule.per_meter and rule.applies_to(meter):
                    yield rule, meter, rule.evaluate(building, meter, now)
        for rule in self.rules:
            if not rule.per_meter:
                yield rule, None, rule.evaluate(building, None, now)

    def detect(self, building, now=None):
        """Create alerts for new findings and return the created EnergyAlert rows."""
        now = now or timezone.now()
        created = []
        for rule, meter, finding in self._findings(building, now):
            if finding is None:
                continue
            if EnergyAlert.objects.filter(building=building, meter=meter, alert_type=rule.alert_type,
                                          is_resolved=False).exists():
                continue
            created.append(EnergyAlert.objects.create(
                building=building, meter=meter, severity=finding.severity, alert_type=rule.alert_type,
                message=finding.message, value_recorded=finding.value, threshold_value=finding.threshold))
        return created


def detect_alerts(building, now=None):
    """Convenience wrapper used by the API: run the default rule set."""
    return AlertDetector().detect(building, now)
