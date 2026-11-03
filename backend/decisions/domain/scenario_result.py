from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScenarioResult:
    new_grid_kwh: Decimal
    monthly_cost_eur: Decimal
    savings_eur: Decimal

    def to_dict(self):
        return {
            "new_grid_kwh": str(self.new_grid_kwh),
            "monthly_cost_eur": str(self.monthly_cost_eur),
            "savings_eur": str(self.savings_eur),
        }
