from datetime import date
from decimal import Decimal
from ..errors import InvalidTariffError


class TariffPlan:
    DEFAULT_PRICE = Decimal("0.30")

    def __init__(self, tariff_id, eur_per_kwh=None, valid_from=None):
        self.id = tariff_id
        self.eur_per_kwh = None
        self.valid_from = None
        self.reset()
        if eur_per_kwh is not None:
            self.set_eur_per_kwh(eur_per_kwh)
        if valid_from is not None:
            self.set_valid_from(valid_from)

    def get_eur_per_kwh(self):
        return self.eur_per_kwh

    def get_valid_from(self):
        return self.valid_from

    def set_eur_per_kwh(self, price):
        price = Decimal(str(price))
        if price <= 0:
            raise InvalidTariffError("Price per kWh must be positive")
        self.eur_per_kwh = price

    def set_valid_from(self, valid_from):
        if not isinstance(valid_from, date):
            raise InvalidTariffError("valid_from must be a date")
        self.valid_from = valid_from

    def reset(self):
        self.eur_per_kwh = TariffPlan.DEFAULT_PRICE
        self.valid_from = date.today()

    def price_at(self, moment):
        return self.eur_per_kwh
