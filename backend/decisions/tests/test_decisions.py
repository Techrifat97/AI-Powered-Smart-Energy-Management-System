import unittest
from decimal import Decimal

from backend.decisions.domain.energy_budget import EnergyBudget
from backend.decisions.domain.notification import Notification
from backend.decisions.domain.tariff_plan import TariffPlan
from backend.decisions.services.alert_service import AlertService
from backend.decisions.services.baseline_anomaly_detector import BaselineAnomalyDetector
from backend.decisions.services.cost_calculator import CostCalculator
from backend.decisions.services.scenario_simulator import ScenarioSimulator


class TariffPlanTests(unittest.TestCase):
    def test_defaults_setters_and_reset(self):
        tariff = TariffPlan(1)
        self.assertEqual(tariff.get_eur_per_kwh(), Decimal("0.30"))
        tariff.set_eur_per_kwh("0.25")
        self.assertEqual(tariff.price_at(None), Decimal("0.25"))
        tariff.reset()
        self.assertEqual(tariff.get_eur_per_kwh(), Decimal("0.30"))

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            TariffPlan(1, eur_per_kwh=0)
        with self.assertRaises(ValueError):
            TariffPlan(1).set_valid_from("today")


class EnergyBudgetTests(unittest.TestCase):
    def test_spending_and_overrun(self):
        budget = EnergyBudget(1, 1200)
        budget.add_cost("43.50")
        self.assertEqual(budget.remaining(), Decimal("1156.50"))
        self.assertTrue(budget.is_overrun(1305))
        self.assertFalse(budget.is_overrun(1143))

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            EnergyBudget(1, 0)
        with self.assertRaises(ValueError):
            EnergyBudget(1, 100).add_cost(-1)


class NotificationTests(unittest.TestCase):
    def test_acknowledge(self):
        note = Notification(1, "Budget exceeded", "HIGH")
        self.assertFalse(note.is_acknowledged())
        note.acknowledge()
        self.assertTrue(note.is_acknowledged())

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            Notification(1, "")
        with self.assertRaises(ValueError):
            Notification(1, "x", "URGENT")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.calculator = CostCalculator(TariffPlan(1))

    def test_demo_case_cost(self):
        self.assertEqual(self.calculator.estimate(145), Decimal("43.50"))
        self.assertEqual(self.calculator.project_month(145), Decimal("1305.00"))

    def test_scenario_hvac_minus_15(self):
        summary = {"net_grid_kwh": 145, "categories": {"HVAC": 120}}
        result = ScenarioSimulator(self.calculator).run(summary, {"HVAC": 15})
        self.assertEqual(result.new_grid_kwh, Decimal("127"))
        self.assertEqual(result.monthly_cost_eur, Decimal("1143.00"))
        self.assertEqual(result.savings_eur, Decimal("162.00"))
        with self.assertRaises(ValueError):
            ScenarioSimulator(self.calculator).run(summary, {"HVAC": 120})

    def test_detector_rates_severity(self):
        detector = BaselineAnomalyDetector(30)
        found = detector.detect({10: 142, 11: 100}, {10: 100, 11: 100})
        self.assertEqual([a["hour"] for a in found], [10])
        self.assertEqual(found[0]["severity"], "LOW")
        high = detector.detect({10: 170}, {10: 100})
        self.assertEqual(high[0]["severity"], "HIGH")

    def test_alert_service_budget_and_anomaly(self):
        service = AlertService(BaselineAnomalyDetector(30), EnergyBudget(1, 1200))
        created = service.check_and_notify(1305, {10: 142}, {10: 100})
        self.assertEqual(len(created), 2)
        created[0].acknowledge()
        self.assertEqual(len(service.pending()), 1)


if __name__ == "__main__":
    unittest.main()
