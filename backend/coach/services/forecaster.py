from datetime import datetime, time, timedelta, timezone as utc_timezone
from math import fsum

from django.utils import timezone

from monitoring.services.aggregation import building_energy_report
from coach.models import ConsumptionForecast


class ConsumptionForecaster:
    """Small heuristic forecast; needs two complete UTC days in the past 14 days.

    Partial days and missing days are not extrapolated. Bands are illustrative,
    not statistically calibrated confidence intervals. Baseline is reference only.
    """

    def __init__(self, horizon_days=7):
        self.horizon_days = horizon_days
        self.availability = {}
        self.history = None

    def generate_forecast(self, building):
        today = timezone.now().astimezone(utc_timezone.utc).date()
        end = datetime.combine(today, time.min, tzinfo=utc_timezone.utc)
        self.history = building_energy_report(building, start=end - timedelta(days=14), end=end)
        days = self.history['complete_days']
        summary = self.history['summary']
        ready = summary['main_data_available'] and len(days) >= 2
        self.availability = {
            'available': ready,
            'reason': 'available' if ready else summary['main_data_reason']
            if not summary['main_data_available'] else 'need_two_complete_utc_days',
            'complete_days_count': len(days),
            'history_start': end - timedelta(days=14), 'history_end': end,
            'observed_full_day_average_kwh': fsum(d['gross_kwh'] for d in days) / len(days) if days else None,
            'method': 'heuristic_weekday_profile; bands_are_not_calibrated',
        }
        if not ready:
            # Never return previously stored forecasts as if they used current data.
            return []
        average = self.availability['observed_full_day_average_kwh']
        baseline = building.baseline_kwh_per_day
        trend = 'STABLE'
        if baseline > 0 and average > baseline * 1.10:
            trend = 'INCREASING'
        elif baseline > 0 and average < baseline * .90:
            trend = 'DECREASING'
        results = []
        for offset in range(self.horizon_days):
            target = today + timedelta(days=offset + 1)
            weekend = target.weekday() >= 5
            drift = 1 + (.005 * offset if trend == 'INCREASING' else -.005 * offset if trend == 'DECREASING' else 0)
            predicted = round(average * (.72 if weekend else 1.08) * drift, 2)
            margin = .08 + .01 * offset
            values = dict(predicted_kwh=predicted,
                          confidence_lower_kwh=round(predicted * (1 - margin), 2),
                          confidence_upper_kwh=round(predicted * (1 + margin), 2), trend=trend)
            ConsumptionForecast.objects.update_or_create(building=building, forecast_date=target, defaults=values)
            results.append(dict(values, forecast_date=target.isoformat(), day_name=target.strftime('%A'), is_weekend=weekend))
        return results
