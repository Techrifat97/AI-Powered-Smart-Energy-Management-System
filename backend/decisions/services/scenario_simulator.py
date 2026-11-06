from decimal import Decimal

from ..domain.scenario_result import ScenarioResult
from ..errors import InvalidScenarioError


class ScenarioSimulator:
    def __init__(self, calculator):
        self.calculator = calculator

    def run(self, summary, changes):
        grid_kwh = Decimal(str(summary["net_grid_kwh"]))
        saved_kwh = Decimal("0")
        for category, percent in changes.items():
            percent = Decimal(str(percent))
            if not Decimal("0") <= percent <= Decimal("100"):
                raise InvalidScenarioError("Reduction must be between 0 and 100 percent")
            saved_kwh += Decimal(str(summary["categories"].get(category, 0))) * percent / 100
        new_grid_kwh = grid_kwh - saved_kwh
        old_cost = self.calculator.project_month(grid_kwh)
        new_cost = self.calculator.project_month(new_grid_kwh)
        return ScenarioResult(new_grid_kwh, new_cost, old_cost - new_cost)
