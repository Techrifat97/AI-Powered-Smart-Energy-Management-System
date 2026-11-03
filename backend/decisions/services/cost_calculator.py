from decimal import Decimal

CENT = Decimal("0.01")


class CostCalculator:
    DAYS_PER_MONTH = 30

    def __init__(self, tariff):
        self.tariff = tariff

    def estimate(self, net_kwh):
        net_kwh = Decimal(str(net_kwh))
        if net_kwh < 0:
            raise ValueError("Energy cannot be negative")
        return (net_kwh * self.tariff.get_eur_per_kwh()).quantize(CENT)

    def project_month(self, daily_net_kwh):
        return (self.estimate(daily_net_kwh) * CostCalculator.DAYS_PER_MONTH).quantize(CENT)
