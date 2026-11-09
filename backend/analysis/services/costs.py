"""MVP tariff scenario: one active global tariff, UTC time bands, no battery.

The active tariff is explicitly applied to the entire selected history as a
scenario; the schema has no effective dates or per-building contracts. These are
estimates, never invoices. Crossing unequal rate bands needs finer measurements.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

from analysis.models import TariffPlan
from monitoring.services.aggregation import building_energy_report


def _interval_rate(row, tariff):
    standard, peak = tariff.rate_standard_eur_per_kwh, tariff.rate_peak_eur_per_kwh
    if standard == peak:
        return Decimal(str(standard))
    start, end = row['start'], row['end']
    boundaries = [start, end]
    day = start.astimezone(timezone.utc).date()
    while day <= end.astimezone(timezone.utc).date():
        for hour in (tariff.peak_start_hour, tariff.peak_end_hour):
            boundary = datetime.combine(day, time(hour), tzinfo=timezone.utc)
            if start < boundary < end:
                boundaries.append(boundary)
        day += timedelta(days=1)
    rates = set()
    for point in sorted(boundaries)[:-1]:
        hour = point.astimezone(timezone.utc).hour
        a, b = tariff.peak_start_hour, tariff.peak_end_hour
        in_peak = a <= hour < b if a < b else hour >= a or hour < b
        rates.add(Decimal(str(peak if in_peak else standard)))
    return rates.pop() if len(rates) == 1 else None


def cost_analysis(building):
    report = building_energy_report(building)
    summary = report['summary']
    tariffs = list(TariffPlan.objects.filter(is_active=True)[:2])
    tariff = tariffs[0] if len(tariffs) == 1 else None
    reason = 'missing_active_tariff' if not tariffs else 'ambiguous_active_tariffs' if len(tariffs) > 1 else 'available'
    if tariff and (any(not isfinite(v) or v < 0 for v in [tariff.rate_standard_eur_per_kwh,
            tariff.rate_peak_eur_per_kwh, tariff.solar_feed_in_eur_per_kwh])
            or not 0 <= tariff.peak_start_hour <= 23 or not 0 <= tariff.peak_end_hour <= 23
            or tariff.peak_start_hour == tariff.peak_end_hour):
        reason = 'invalid_tariff'
    if reason == 'available' and not summary['grid_estimates_available']:
        reason = summary['grid_estimates_reason']
    totals = None
    if reason == 'available':
        totals = {'gross': Decimal(0), 'imports': Decimal(0), 'exports': Decimal(0), 'self_consumption': Decimal(0)}
        feed_in = Decimal(str(tariff.solar_feed_in_eur_per_kwh))
        for row in report['grid_intervals']:
            rate = _interval_rate(row, tariff)
            if rate is None:
                reason, totals = 'interval_crosses_tariff_band', None
                break
            totals['gross'] += Decimal(str(row['energy_kwh'])) * rate
            totals['imports'] += Decimal(str(row['import_kwh'])) * rate
            totals['exports'] += Decimal(str(row['export_kwh'])) * feed_in
            totals['self_consumption'] += Decimal(str(min(row['energy_kwh'], row['solar_kwh']))) * rate
    def money(key):
        return float(totals[key].quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if totals is not None else None
    net = float((totals['imports'] - totals['exports']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if totals is not None else None
    covered = totals is not None and summary['main_coverage_complete']
    return {
        'building_id': building.pk, 'building_name': building.name,
        'tariff_applied': tariff.name if tariff else None,
        'rate_eur_per_kwh': tariff.rate_standard_eur_per_kwh if tariff and reason != 'invalid_tariff' else None,
        'total_consumption_kwh': summary['total_consumption_kwh'],
        'solar_generated_kwh': summary['total_solar_generated_kwh'],
        # Legacy totals require continuous coverage of the reported scope.
        'gross_cost_eur': money('gross') if covered else None,
        'solar_savings_eur': money('self_consumption') if covered else None,
        'net_cost_eur': net if covered else None,
        'estimated_import_cost_eur': money('imports'),
        'estimated_export_credit_eur': money('exports'),
        'estimated_net_cost_eur': net,
        'estimated_grid_import_kwh': summary['estimated_grid_import_kwh'],
        'estimated_grid_export_kwh': summary['estimated_grid_export_kwh'],
        'cost_estimates_available': totals is not None, 'cost_estimates_reason': reason,
        'coverage_complete': summary['main_coverage_complete'],
        'complete_bill_available': False,
        'pricing_scope': 'one active global tariff applied to recorded history; scenario, not an invoice',
        'tariff_timezone': 'UTC', 'energy_summary': summary,
    }
