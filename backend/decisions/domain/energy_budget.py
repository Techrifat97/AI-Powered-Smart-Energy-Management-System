from decimal import Decimal


class EnergyBudget:
    def __init__(self, budget_id, monthly_limit_eur):
        self.id = budget_id
        self.monthly_limit_eur = None
        self._spent_eur = Decimal("0")
        self.set_monthly_limit_eur(monthly_limit_eur)

    def get_monthly_limit_eur(self):
        return self.monthly_limit_eur

    def get_spent_eur(self):
        return self._spent_eur

    def set_monthly_limit_eur(self, limit):
        limit = Decimal(str(limit))
        if limit <= 0:
            raise ValueError("Monthly limit must be positive")
        self.monthly_limit_eur = limit

    def add_cost(self, eur):
        eur = Decimal(str(eur))
        if eur < 0:
            raise ValueError("Cost cannot be negative")
        self._spent_eur += eur

    def reset_spending(self):
        self._spent_eur = Decimal("0")

    def remaining(self):
        return self.monthly_limit_eur - self._spent_eur

    def is_overrun(self, projected):
        return Decimal(str(projected)) > self.monthly_limit_eur
