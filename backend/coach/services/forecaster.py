from datetime import timedelta, date
from django.utils import timezone
from django.db.models import Sum, Avg
from monitoring.models import Building, EnergyReading
from coach.models import ConsumptionForecast


class ConsumptionForecaster:
    """
    Service responsible for transforming S1 historical meter telemetry
    into multi-step predictive consumption forecasts.
    """

    def __init__(self, horizon_days: int = 7):
        self.horizon_days = horizon_days

    def generate_forecast(self, building: Building) -> list:
        """
        Generates 7-day future predictions for the given building.
        Persists or updates records in ConsumptionForecast.
        """
        # 1. Fetch recent daily totals from S1 monitoring readings
        recent_readings = EnergyReading.objects.filter(
            meter__building=building,
            meter__meter_type__in=['ELECTRICITY', 'HVAC', 'LIGHTING']
        ).order_by('timestamp')

        # Baseline reference
        baseline = building.baseline_kwh_per_day or 200.0

        if recent_readings.exists():
            latest_time = recent_readings.last().timestamp
            # Calculate average daily consumption over the last 14 days
            start_window = latest_time - timedelta(days=14)
            window_readings = recent_readings.filter(timestamp__gte=start_window)

            total_kwh = window_readings.aggregate(total=Sum('energy_kwh'))['total'] or 0.0
            earliest_in_win = window_readings.first().timestamp
            span_days = max(1.0, (latest_time - earliest_in_win).total_seconds() / 86400.0)
            avg_daily_kwh = total_kwh / span_days
            start_date = latest_time.date() + timedelta(days=1)
        else:
            avg_daily_kwh = baseline
            start_date = timezone.now().date() + timedelta(days=1)

        # 2. Trend analysis (compare first half of window vs second half)
        trend = 'STABLE'
        if avg_daily_kwh > baseline * 1.10:
            trend = 'INCREASING'
        elif avg_daily_kwh < baseline * 0.90:
            trend = 'DECREASING'

        forecast_results = []

        # 3. Predict day by day with day-of-week profile
        for day_offset in range(self.horizon_days):
            target_date = start_date + timedelta(days=day_offset)
            is_weekend = target_date.weekday() >= 5  # 5=Sat, 6=Sun

            # Commercial / educational buildings typically drop 25-35% on weekends
            profile_factor = 0.72 if is_weekend else 1.08

            # Small variation based on day offset
            trend_drift = 1.0 + (0.005 * day_offset if trend == 'INCREASING' else (-0.005 * day_offset if trend == 'DECREASING' else 0.0))
            predicted = round(avg_daily_kwh * profile_factor * trend_drift, 2)

            # Confidence bounds (+- 8% for near days, widening to +- 14% at 7 days)
            error_margin_pct = 0.08 + (0.01 * day_offset)
            lower_bound = round(predicted * (1.0 - error_margin_pct), 2)
            upper_bound = round(predicted * (1.0 + error_margin_pct), 2)

            # Save or update forecast in database
            forecast_obj, _ = ConsumptionForecast.objects.update_or_create(
                building=building,
                forecast_date=target_date,
                defaults={
                    'predicted_kwh': predicted,
                    'confidence_lower_kwh': lower_bound,
                    'confidence_upper_kwh': upper_bound,
                    'trend': trend,
                }
            )

            forecast_results.append({
                'forecast_date': target_date.isoformat(),
                'day_name': target_date.strftime('%A'),
                'is_weekend': is_weekend,
                'predicted_kwh': predicted,
                'confidence_lower_kwh': lower_bound,
                'confidence_upper_kwh': upper_bound,
                'trend': trend,
            })

        return forecast_results

