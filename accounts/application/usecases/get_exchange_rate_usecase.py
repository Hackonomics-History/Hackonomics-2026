from typing import Dict

from accounts.application.ports.repository import AccountRepository
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class GetExchangeRateUseCase:
    def __init__(self, repository: AccountRepository, exchange_service):
        self.repository = repository
        self.exchange_service = exchange_service

    def execute(self, user_id: str) -> Dict[str, str | float]:
        account = self.repository.find_by_user_id(user_id)

        if not account:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)
        if account.country is None:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        currency = account.country.currency.upper()
        rate = self.exchange_service.get_usd_to_currency(currency)

        return {
            "base": "USD",
            "target": currency,
            "rate": rate,
        }
