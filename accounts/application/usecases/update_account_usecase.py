from decimal import Decimal

from accounts.application.dto import AccountUpdateCommand
from accounts.application.ports.event_publisher import DomainEventPublisher
from accounts.application.ports.repository import AccountRepository
from accounts.domain.entities import Account
from accounts.domain.events import AccountEventType
from accounts.domain.value_objects import AnnualIncome, Country
from common.errors.exceptions import BusinessException
from common.errors.handlers import ErrorCode


class UpdateAccountUseCase:
    def __init__(
        self,
        repository: AccountRepository,
        event_publisher: DomainEventPublisher,
    ):
        self.repository = repository
        self.event_publisher = event_publisher

    def execute(self, user_id: str, command: AccountUpdateCommand) -> None:
        if not user_id:
            raise BusinessException(ErrorCode.UNAUTHORIZED)

        account = self.repository.find_by_user_id(user_id)

        # Create new Account
        if account is None:
            country_code = command.country_code or "CA"
            currency = command.currency or "CAD"
            annual_income = command.annual_income or Decimal("1.00")
            monthly_amount = command.monthly_investable_amount or Decimal("0.00")

            account = Account(
                user_id=user_id,
                country=Country(
                    code=country_code,
                    currency=currency,
                ),
                income=AnnualIncome(annual_income),
                monthly_investable_amount=monthly_amount,
            )
            self.repository.save(account)

            self.event_publisher.publish(
                aggregate_type="Account",
                aggregate_id=str(user_id),
                event_type=AccountEventType.ACCOUNT_CREATED,
                payload={"user_id": user_id},
            )
            return
        # Edit (Update)
        if command.country_code and command.currency:
            country = Country(
                code=command.country_code,
                currency=command.currency,
            )
            account.update_country(country)

        if command.annual_income is not None:
            income = AnnualIncome(command.annual_income)
            account.update_income(income)

        if command.monthly_investable_amount is not None:
            account.update_monthly_investable_amount(command.monthly_investable_amount)

        self.repository.save(account)
        self.event_publisher.publish(
            aggregate_type="Account",
            aggregate_id=str(user_id),
            event_type=AccountEventType.ACCOUNT_UPDATED,
            payload={
                "user_id": user_id,
                "country_code": account.country.code if account.country else None,
                "currency": account.country.currency if account.country else None,
                "annual_income": str(account.income.amount) if account.income else None,
                "monthly_investable_amount": (
                    str(account.monthly_investable_amount)
                    if account.monthly_investable_amount is not None
                    else None
                ),
            },
        )
