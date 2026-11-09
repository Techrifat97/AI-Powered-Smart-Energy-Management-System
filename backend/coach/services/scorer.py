class SustainabilityScorer:
    """Illustrative score and carbon scenario, using matched-interval imports.

    The fixed emission factor is a scenario assumption, not a measured footprint.
    Monetary estimates belong to S3's explicit tariff calculation.
    """
    GRID_CARBON_FACTOR_KG_PER_KWH = 0.385

    @classmethod
    def evaluate(cls, current_daily_kwh, baseline_daily_kwh, solar_daily_kwh=None, *, import_daily_kwh=None):
        ready = (current_daily_kwh is not None and solar_daily_kwh is not None
                 and baseline_daily_kwh is not None and baseline_daily_kwh > 0)
        variance = ((current_daily_kwh - baseline_daily_kwh) / baseline_daily_kwh * 100) if ready else None
        score = max(0, min(100, round(75 - variance * .8 + solar_daily_kwh / baseline_daily_kwh * 20, 1))) if ready else None
        grade = next((label for threshold, label in [(90, 'A+'), (80, 'A'), (70, 'B'), (60, 'C'), (50, 'D'), (0, 'F')]
                      if score >= threshold), None) if ready else None
        return {
            'available': ready,
            'reason': 'available' if ready else 'missing_daily_measurements_or_positive_baseline',
            'sustainability_score': score, 'efficiency_grade': grade,
            'variance_from_baseline_pct': round(variance, 1) if ready else None,
            'daily_carbon_kg_co2': round(import_daily_kwh * cls.GRID_CARBON_FACTOR_KG_PER_KWH, 2)
            if import_daily_kwh is not None else None,
            'carbon_factor_kg_per_kwh': cls.GRID_CARBON_FACTOR_KG_PER_KWH,
            'estimated_daily_cost_eur': None,
            'solar_offset_ratio': round(solar_daily_kwh / current_daily_kwh, 2)
            if ready and current_daily_kwh > 0 else None,
        }
