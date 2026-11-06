import unittest

from backend.decisions.domain.energy_budget import EnergyBudget
from backend.decisions.domain.notification import Notification
from backend.decisions.domain.tariff_plan import TariffPlan
from backend.decisions.errors import (
    DecisionsError,
    DecisionsErrorHandler,
    InvalidBudgetError,
    InvalidEnergyValueError,
    InvalidNotificationError,
    InvalidScenarioError,
    InvalidTariffError,
    InvalidThresholdError,
)
from backend.decisions.services.baseline_anomaly_detector import BaselineAnomalyDetector
from backend.decisions.services.cost_calculator import CostCalculator
from backend.decisions.services.scenario_simulator import ScenarioSimulator


class DecisionsExceptionTests(unittest.TestCase):
    def test_hierarchy_keeps_value_error_compatibility(self):
        self.assertTrue(issubclass(InvalidTariffError, DecisionsError))
        self.assertTrue(issubclass(InvalidTariffError, ValueError))

    def test_zero_price_raises_invalid_tariff(self):
        with self.assertRaises(InvalidTariffError):
            TariffPlan(1, eur_per_kwh=0)

    def test_negative_cost_raises_invalid_budget(self):
        with self.assertRaises(InvalidBudgetError):
            EnergyBudget(1, 100).add_cost(-1)

    def test_unknown_severity_raises_invalid_notification(self):
        with self.assertRaises(InvalidNotificationError):
            Notification(1, "x", "URGENT")

    def test_negative_energy_raises_invalid_energy_value(self):
        with self.assertRaises(InvalidEnergyValueError):
            CostCalculator(TariffPlan(1)).estimate(-5)

    def test_reduction_over_100_raises_invalid_scenario(self):
        summary = {"net_grid_kwh": 145, "categories": {"HVAC": 120}}
        simulator = ScenarioSimulator(CostCalculator(TariffPlan(1)))
        with self.assertRaises(InvalidScenarioError):
            simulator.run(summary, {"HVAC": 120})

    def test_zero_threshold_raises_invalid_threshold(self):
        with self.assertRaises(InvalidThresholdError):
            BaselineAnomalyDetector(0)


class DecisionsErrorHandlerTests(unittest.TestCase):
    def setUp(self):
        self.handler = DecisionsErrorHandler()

    def test_safe_call_returns_value_on_success(self):
        result = self.handler.safe_call(EnergyBudget, 1, 1200)
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["value"], EnergyBudget)

    def test_safe_call_turns_error_into_result_with_code(self):
        result = self.handler.safe_call(EnergyBudget, 1, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "INVALID_BUDGET")

    def test_safe_call_labels_unexpected_errors(self):
        result = self.handler.safe_call(CostCalculator(TariffPlan(1)).estimate, "abc")
        self.assertEqual(result["code"], "UNEXPECTED_ERROR")


if __name__ == "__main__":
    unittest.main()
