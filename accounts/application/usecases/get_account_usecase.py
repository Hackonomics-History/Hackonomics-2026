from typing import Dict, Optional

from accounts.application.ports.repository import AccountRepository


class GetAccountUseCase:
    def __init__(self, repository: AccountRepository):
        self.repository = repository

    def execute(self, user_id: str) -> Optional[Dict[str, str]]:
        account = self.repository.find_by_user_id(user_id)

        if account is None:
            return None

        country = account.country
        income = account.income
        monthly_amount = account.monthly_investable_amount

        if country is None or income is None or monthly_amount is None:
            return None

        return {
            "country_code": country.code,
            "currency": country.currency,
            "annual_income": str(income.amount),
            "monthly_investable_amount": str(monthly_amount),
        }
