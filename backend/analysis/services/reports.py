"""Stored cost reports for a fully covered, inclusive UTC date range."""
from datetime import datetime, time, timedelta, timezone

from analysis.models import CostReport, TariffPlan
from .costs import cost_analysis
from .errors import ReportUnavailable  # noqa: F401  (re-exported for callers)


def generate_cost_report(building, period_start, period_end):
    """Create a CostReport from the active tariff, or raise ReportUnavailable.

    Both dates are inclusive UTC days. The period must be continuously covered by
    recorded main readings; otherwise no report is stored.
    """
    if period_start > period_end:
        raise ReportUnavailable('period_start_after_period_end')
    start = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    analysis = cost_analysis(building, start=start, end=end)
    if not analysis['cost_estimates_available']:
        raise ReportUnavailable(analysis['cost_estimates_reason'])
    if not analysis['coverage_complete']:
        raise ReportUnavailable('period_not_fully_covered')
    return CostReport.objects.create(
        building=building,
        tariff=TariffPlan.objects.filter(is_active=True).first(),
        period_start=period_start, period_end=period_end,
        total_grid_kwh=analysis['estimated_grid_import_kwh'],
        total_cost_eur=analysis['estimated_net_cost_eur'],
        solar_savings_eur=analysis['solar_savings_eur'],
    )
