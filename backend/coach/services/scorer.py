class SustainabilityScorer:
    """
    Evaluates building energy efficiency and environmental impact.
    Uses European average grid emission factor: 0.385 kg CO2e / kWh.
    """
    GRID_CARBON_FACTOR_KG_PER_KWH = 0.385
    ELECTRICITY_COST_EUR_PER_KWH = 0.32

    @classmethod
    def evaluate(cls, current_daily_kwh: float, baseline_daily_kwh: float, solar_daily_kwh: float = 0.0) -> dict:
        """
        Calculates sustainability score (0-100), carbon footprint, and energy grade.
        """
        baseline = max(1.0, baseline_daily_kwh)
        net_consumption = max(0.0, current_daily_kwh - solar_daily_kwh)

        # Variance relative to baseline
        variance_pct = round(((current_daily_kwh - baseline) / baseline) * 100.0, 1)

        # Sustainability score: baseline = 75 points.
        # Less consumption or solar surplus boosts score towards 100.
        # Excess consumption penalizes score towards 0.
        raw_score = 75.0 - (variance_pct * 0.8) + (solar_daily_kwh / baseline * 20.0)
        score = max(0.0, min(100.0, round(raw_score, 1)))

        if score >= 90:
            grade = 'A+'
        elif score >= 80:
            grade = 'A'
        elif score >= 70:
            grade = 'B'
        elif score >= 60:
            grade = 'C'
        elif score >= 50:
            grade = 'D'
        else:
            grade = 'F'

        carbon_kg = round(net_consumption * cls.GRID_CARBON_FACTOR_KG_PER_KWH, 2)
        daily_cost_eur = round(net_consumption * cls.ELECTRICITY_COST_EUR_PER_KWH, 2)

        return {
            'sustainability_score': score,
            'efficiency_grade': grade,
            'variance_from_baseline_pct': variance_pct,
            'daily_carbon_kg_co2': carbon_kg,
            'estimated_daily_cost_eur': daily_cost_eur,
            'solar_offset_ratio': round(solar_daily_kwh / max(1.0, current_daily_kwh), 2),
        }

