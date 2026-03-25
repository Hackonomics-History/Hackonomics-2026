from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from accounts.domain.value_objects import AnnualIncome, Country


@dataclass
class Account:
    # Ory identity UUID — the Go BFF is the source of truth for this value
    user_id: str
    country: Optional[Country]
    income: Optional[AnnualIncome]
    monthly_investable_amount: Optional[Decimal]

    def update_country(self, country: Country):
        self.country = country

    def update_income(self, income: AnnualIncome):
        self.income = income

    def update_monthly_investable_amount(self, amount: Decimal):
        self.monthly_investable_amount = amount
