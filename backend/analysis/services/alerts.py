"""Rule-based alert detection over recorded S1 readings.

Simple, explainable thresholds, not a statistical anomaly model. Detection is
conservative: with too little data a rule stays silent. An unresolved alert of
the same type for the same building/meter is never duplicated.
"""
from datetime import timedelta
from math import fsum

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


def _mean(values):
    return fsum(values) / len(values)


def _main_series(meter, now):
    rows = EnergyReading.objects.filter(meter=meter, timestamp__lte=now, timestamp__gt=now - WINDOW)
    return list(rows.order_by('timestamp').values_list('timestamp', 'power_kw'))


def _peak_spike(meter, now):
    series = _main_series(meter, now)
    if len(series) <= MIN_SAMPLES:
        return None
    *earlier, (_, latest) = series
    average = _mean([p for _, p in earlier])
    threshold = average * PEAK_SPIKE_FACTOR
    if average > 0 and latest > threshold:
        return ('WARNING', f'Power of {latest:.2f} kW is above {PEAK_SPIKE_FACTOR:g}x the 24 h '
                f'average of {average:.2f} kW.', latest, threshold)


def _night_load(meter, now):
    series = _main_series(meter, now)
    night = [p for t, p in series if t.hour in NIGHT_HOURS_UTC]
    day = [p for t, p in series if t.hour not in NIGHT_HOURS_UTC]
    if len(night) < MIN_SAMPLES or len(day) < MIN_SAMPLES:
        return None
    night_avg, threshold = _mean(night), _mean(day) * NIGHT_LOAD_FACTOR
    if night_avg > threshold:
        return ('WARNING', f'Night-time (UTC) average power of {night_avg:.2f} kW exceeds '
                f'{NIGHT_LOAD_FACTOR:.0%} of the daytime average.', night_avg, threshold)


def _offline(meter, now):
    latest = meter.readings.order_by('-timestamp').first()
    if latest is None:
        return None
    seconds = latest.interval_seconds or 0
    last_seen = latest.timestamp + timedelta(seconds=seconds)
    if now - last_seen > OFFLINE_AFTER:
        minutes = (now - last_seen).total_seconds() / 60
        return ('CRITICAL', f'No reading from meter {meter.device_id} for {minutes:.0f} minutes.',
                minutes, OFFLINE_AFTER.total_seconds() / 60)


def _budget(building):
    if not building.baseline_kwh_per_day or building.baseline_kwh_per_day <= 0:
        return None
    days = building_energy_report(building)['complete_days']
    if not days:
        return None
    latest = days[-1]
    if latest['gross_kwh'] > building.baseline_kwh_per_day:
        return ('WARNING', f"Consumption of {latest['gross_kwh']:.1f} kWh on {latest['date']} exceeded "
                f"the daily baseline of {building.baseline_kwh_per_day:.1f} kWh.",
                latest['gross_kwh'], building.baseline_kwh_per_day)


def detect_alerts(building, now=None):
    """Create alerts for new findings and return the created EnergyAlert rows."""
    now = now or timezone.now()
    findings = []
    for meter in Meter.objects.filter(building=building, is_active=True):
        if meter.meter_type == 'ELECTRICITY':
            findings.append(('PEAK_SPIKE', meter, _peak_spike(meter, now)))
            findings.append(('UNUSUAL_NIGHT_LOAD', meter, _night_load(meter, now)))
        findings.append(('METER_OFFLINE', meter, _offline(meter, now)))
    findings.append(('BUDGET_EXCEEDED', None, _budget(building)))

    created = []
    for alert_type, meter, found in findings:
        if found is None:
            continue
        if EnergyAlert.objects.filter(building=building, meter=meter, alert_type=alert_type,
                                      is_resolved=False).exists():
            continue
        severity, message, value, threshold = found
        created.append(EnergyAlert.objects.create(
            building=building, meter=meter, severity=severity, alert_type=alert_type,
            message=message, value_recorded=value, threshold_value=threshold))
    return created
