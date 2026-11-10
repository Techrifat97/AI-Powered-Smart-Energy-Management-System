"""What-if cost scenarios over recorded intervals.

A scenario re-prices the building's recorded history with optional changes:
an alternative tariff, a consumption change and a solar-output change. It uses
the same exact-interval, no-battery assumptions as the cost estimate.
"""
from decimal import Decimal, ROUND_HALF_UP

from analysis.models import TariffPlan
from monitoring.services.aggregation import building_energy_report
from .costs import _interval_rate


def _money(value):
    return float(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def _price(intervals, tariff, consumption_factor, solar_factor):
    imports = exports = Decimal(0)
    import_kwh = export_kwh = 0.0
    feed_in = Decimal(str(tariff.solar_feed_in_eur_per_kwh))
    for row in intervals:
        rate = _interval_rate(row, tariff)
        if rate is None:
            return None
        consumption = row['energy_kwh'] * consumption_factor
        solar = row['solar_kwh'] * solar_factor
        imported, exported = max(consumption - solar, 0.0), max(solar - consumption, 0.0)
        imports += Decimal(str(imported)) * rate
        exports += Decimal(str(exported)) * feed_in
        import_kwh += imported
        export_kwh += exported
    return {'import_kwh': import_kwh, 'export_kwh': export_kwh, 'import_cost_eur': _money(imports),
            'export_credit_eur': _money(exports), 'net_cost_eur': _money(imports - exports)}


def run_scenario(building, *, tariff=None, consumption_change_pct=0.0, solar_change_pct=0.0):
    """Compare the active tariff on recorded data with a modified scenario.

    `tariff` is an unsaved TariffPlan-like object (None keeps the active tariff).
    Percentages are signed changes, e.g. -10 reduces consumption by 10 %.
    """
    report = building_energy_report(building)
    summary = report['summary']
    active = list(TariffPlan.objects.filter(is_active=True)[:2])
    result = {'building_id': building.pk, 'tariff_timezone': 'UTC',
              'assumptions': {'consumption_change_pct': consumption_change_pct,
                              'solar_change_pct': solar_change_pct,
                              'scenario_tariff': tariff.name if tariff else 'active tariff'},
              'available': False, 'reason': None, 'baseline': None, 'scenario': None,
              'difference_net_cost_eur': None}
    if len(active) != 1:
        result['reason'] = 'missing_active_tariff' if not active else 'ambiguous_active_tariffs'
        return result
    if not summary['grid_estimates_available']:
        result['reason'] = summary['grid_estimates_reason']
        return result
    if not summary['main_coverage_complete']:
        result['reason'] = 'coverage_incomplete'
        return result
    baseline = _price(report['grid_intervals'], active[0], 1.0, 1.0)
    scenario = _price(report['grid_intervals'], tariff or active[0],
                      1 + consumption_change_pct / 100, 1 + solar_change_pct / 100)
    if baseline is None or scenario is None:
        result['reason'] = 'interval_crosses_tariff_band'
        return result
    result.update(available=True, reason='available', baseline=baseline, scenario=scenario,
                  difference_net_cost_eur=round(scenario['net_cost_eur'] - baseline['net_cost_eur'], 2))
    return result
