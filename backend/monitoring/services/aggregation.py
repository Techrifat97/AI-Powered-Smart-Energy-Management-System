"""Shared, conservative interval calculations for S1, S2 and S3.

Intervals are [timestamp, timestamp + interval_seconds). Bounds select interval
starts, without prorating. All-history is the default. Coverage is checked even
against intervals starting before a requested window. An unknown earlier
duration blocks coverage until its provenance has been checked.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as utc_timezone
from math import fsum

from django.utils import timezone

from monitoring.models import Building, EnergyReading

UTC = utc_timezone.utc


def _coverage(rows, blockers=()):
    """Never sum overlapping mains/solar, even on the same physical meter."""
    known = [r for r in rows if r['end'] is not None]
    overlaps = any(a['end'] > b['start'] for a, b in zip(known, known[1:]))
    overlaps |= any(a['start'] < b['end'] and b['start'] < a['end']
                    for a in known for b in blockers if b['end'] is not None)
    unknown = any(r['end'] is None for r in rows)
    unknown_before = bool(rows) and any(r['end'] is None for r in blockers)
    ambiguous = overlaps or ((unknown or unknown_before) and
                             len({r['meter_id'] for r in [*rows, *blockers]}) > 1)
    reason = ('overlapping_intervals' if overlaps else 'unknown_duration_before_window' if unknown_before
              else 'unknown_duration' if unknown
              else 'available' if rows else 'missing_readings')
    return bool(rows) and not (unknown or unknown_before or overlaps), ambiguous, reason


def _continuous(rows, start, end):
    if not rows or rows[0]['start'] != start or rows[-1]['end'] != end:
        return False
    return all(a['end'] == b['start'] for a, b in zip(rows, rows[1:]))


def building_energy_report(building: Building, *, start=None, end=None) -> dict:
    """Return summary plus validated intervals and fully covered UTC-day totals.

    Gross/solar sums refer to recorded intervals, not an extrapolated whole period.
    Gaps are explicit. Multiple mains are accepted only with known nonoverlapping
    coverage. Solar meters are treated conservatively by the same overlap rule.
    Grid estimates assume NO BATTERY and exact main/solar interval matches, or an
    explicit declaration of no solar installation. They cannot recover variations
    within an interval and are not measured imports/exports.
    """
    if not isinstance(building, Building) or building.pk is None:
        raise ValueError('Pass a saved Building object.')
    for name, value in [('start', start), ('end', end)]:
        if value is not None and (not isinstance(value, datetime) or timezone.is_naive(value)):
            raise ValueError(f'{name} must be a timezone-aware datetime.')
    if start is not None and end is not None and start >= end:
        raise ValueError('start must be before end.')

    all_rows = []
    for r in EnergyReading.objects.filter(meter__building=building).order_by('timestamp', 'pk').values(
        'meter_id', 'meter__meter_type', 'timestamp', 'interval_seconds', 'energy_kwh', 'power_kw',
    ):
        duration = r['interval_seconds']
        all_rows.append(dict(r, start=r['timestamp'], end=(r['timestamp'] + timedelta(seconds=duration))
                             if duration is not None else None))
    rows = [r for r in all_rows if (start is None or r['start'] >= start)
            and (end is None or r['start'] < end)]
    main = [r for r in rows if r['meter__meter_type'] == 'ELECTRICITY']
    solar = [r for r in rows if r['meter__meter_type'] == 'SOLAR']
    before = [r for r in all_rows if start is not None and r['start'] < start]
    available, ambiguous, main_reason = _coverage(
        main, [r for r in before if r['meter__meter_type'] == 'ELECTRICITY'])
    solar_available, _, solar_reason = _coverage(
        solar, [r for r in before if r['meter__meter_type'] == 'SOLAR'])
    # A window crossing an interval end cannot claim complete interval measurements.
    if end is not None and any(r['end'] is not None and r['end'] > end for r in main):
        available, main_reason = False, 'interval_crosses_window_end'
    if end is not None and any(r['end'] is not None and r['end'] > end for r in solar):
        solar_available, solar_reason = False, 'interval_crosses_window_end'
    confirmed_no_solar = building.has_solar_installation is False
    earlier_solar = [r for r in before if r['meter__meter_type'] == 'SOLAR']
    prior_solar_may_overlap = bool(main) and any(
        r['end'] is None or r['end'] > start for r in earlier_solar)
    if confirmed_no_solar and (solar or prior_solar_may_overlap):
        solar_available, solar_reason = False, 'installation_status_conflicts_with_readings'
    elif not solar and confirmed_no_solar:
        solar_available, solar_reason = True, 'confirmed_no_installation'

    gross = fsum(r['energy_kwh'] for r in main) if available else None
    solar_total = fsum(r['energy_kwh'] for r in solar) if solar_available else None
    days = len({r['start'].astimezone(UTC).date() for r in main})
    scope_start = start if start is not None else main[0]['start'] if main else None
    scope_end = end if end is not None else main[-1]['end'] if main else None
    continuous = available and _continuous(main, scope_start, scope_end)

    grid, grid_reason = [], main_reason if not available else solar_reason
    if available and solar_available:
        solar_map = {(r['start'], r['end']): r for r in solar}
        if confirmed_no_solar or set(solar_map) == {(r['start'], r['end']) for r in main}:
            for r in main:
                generation = 0.0 if confirmed_no_solar else solar_map[(r['start'], r['end'])]['energy_kwh']
                grid.append(dict(r, solar_kwh=generation,
                                 import_kwh=max(r['energy_kwh'] - generation, 0.0),
                                 export_kwh=max(generation - r['energy_kwh'], 0.0)))
            grid_reason = 'available'
        else:
            grid_reason = 'main_solar_intervals_do_not_match'

    by_day = defaultdict(list)
    if available:
        for r in main:
            by_day[r['start'].astimezone(UTC).date()].append(r)
    complete_days = []
    grid_map = {r['start']: r for r in grid}
    for day, daily_rows in sorted(by_day.items()):
        midnight = datetime.combine(day, time.min, tzinfo=UTC)
        if _continuous(daily_rows, midnight, midnight + timedelta(days=1)):
            complete_days.append({
                'date': day, 'gross_kwh': fsum(r['energy_kwh'] for r in daily_rows),
                'solar_kwh': fsum(grid_map[r['start']]['solar_kwh'] for r in daily_rows) if grid else None,
                'import_kwh': fsum(grid_map[r['start']]['import_kwh'] for r in daily_rows) if grid else None,
            })

    summary = {
        'building_id': building.pk, 'building_name': building.name, 'location': building.location,
        'area_sqm': building.area_sqm, 'baseline_kwh_per_day': building.baseline_kwh_per_day,
        'has_solar_installation': building.has_solar_installation,
        'total_consumption_kwh': gross,
        'average_daily_kwh': gross / days if available else None,
        'peak_demand_kw': max(r['power_kw'] for r in main) if available else None,
        'total_solar_generated_kwh': solar_total,
        'net_grid_consumption_kwh': gross - solar_total if gross is not None and solar_total is not None else None,
        'active_meters_count': building.meters.filter(is_active=True).count(),
        'total_readings_count': len(rows),
        'earliest_reading': rows[0]['start'] if rows else None,
        'latest_reading': rows[-1]['start'] if rows else None,
        'main_meter_count': len({r['meter_id'] for r in main}), 'main_readings_count': len(main),
        'main_data_available': available, 'main_data_ambiguous': ambiguous, 'main_data_reason': main_reason,
        'recorded_main_days_count': days, 'solar_readings_count': len(solar),
        'solar_data_available': solar_available, 'solar_data_reason': solar_reason,
        'main_coverage_complete': bool(continuous),
        'grid_estimates_available': bool(grid), 'grid_estimates_reason': grid_reason,
        'estimated_grid_import_kwh': fsum(r['import_kwh'] for r in grid) if grid else None,
        'estimated_grid_export_kwh': fsum(r['export_kwh'] for r in grid) if grid else None,
        'complete_main_days_count': len(complete_days),
        'full_day_average_kwh': fsum(d['gross_kwh'] for d in complete_days) / len(complete_days) if complete_days else None,
        'scope_start': scope_start, 'scope_end': scope_end,
    }
    return {'summary': summary, 'main_intervals': main if available else [],
            'grid_intervals': grid, 'complete_days': complete_days}


def summarize_building(building: Building, *, start=None, end=None) -> dict:
    """Public S1 summary, including null values and reasons for unavailable data."""
    return building_energy_report(building, start=start, end=end)['summary']
