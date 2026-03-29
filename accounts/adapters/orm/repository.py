from typing import Optional

from accounts.adapters.orm.models import AccountModel
from accounts.application.ports.repository import AccountRepository
from accounts.domain.entities import Account
from accounts.domain.value_objects import AnnualIncome, Country
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class DjangoAccountRepository(AccountRepository):
    def find_by_user_id(self, user_id: str) -> Optional[Account]:
        try:
            m = AccountModel.objects.get(ory_identity_id=user_id)
        except AccountModel.DoesNotExist:
            return None

        if m.country_code is None or m.currency is None or m.annual_income is None:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        return Account(
            user_id=m.ory_identity_id,
            country=Country(m.country_code, m.currency),
            income=AnnualIncome(m.annual_income),
            monthly_investable_amount=m.monthly_investable_amount,
        )

    def get_all_country_codes(self) -> list[str]:
        return list(
            AccountModel.objects.exclude(country_code__isnull=True)
            .values_list("country_code", flat=True)
            .distinct()
        )

    def save(self, account: Account) -> None:
        if account.country is None or account.income is None:
            raise BusinessException(ErrorCode.DATA_NOT_FOUND)

        AccountModel.objects.update_or_create(
            ory_identity_id=account.user_id,
            defaults={
                "country_code": account.country.code,
                "currency": account.country.currency,
                "annual_income": account.income.amount,
                "monthly_investable_amount": account.monthly_investable_amount,
            },
        )
