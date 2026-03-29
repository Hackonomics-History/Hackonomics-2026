from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.adapters.events.event_publisher import AccountDomainEventPublisher
from accounts.adapters.orm.repository import DjangoAccountRepository
from accounts.application.dto import AccountUpdateCommand
from accounts.application.usecases.get_account_usecase import GetAccountUseCase
from accounts.application.usecases.get_exchange_rate_usecase import (
    GetExchangeRateUseCase,
)
from accounts.application.usecases.update_account_usecase import UpdateAccountUseCase
from accounts.presentation.serializers import AccountUpdateSerializer
from common.EmptySerializer import EmptySerializer
from events.adapters.outbox_repository import OutboxEventRepository
from exchange.application.services import ExchangeRateService


class AccountView(GenericAPIView):
    serializer_class = AccountUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usecase = GetAccountUseCase(repository=DjangoAccountRepository())
        result = usecase.execute(user_id=request.user.ory_id)

        if result is None:
            return Response(
                {
                    "country_code": None,
                    "currency": None,
                    "annual_income": None,
                    "monthly_investable_amount": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(result, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = AccountUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        command = AccountUpdateCommand(**serializer.validated_data)

        usecase = UpdateAccountUseCase(
            repository=DjangoAccountRepository(),
            event_publisher=AccountDomainEventPublisher(
                outbox_repository=OutboxEventRepository()
            ),
        )
        usecase.execute(
            user_id=request.user.ory_id,
            command=command,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class MyExchangeRateAPIView(GenericAPIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        usecase = GetExchangeRateUseCase(
            repository=DjangoAccountRepository(),
            exchange_service=ExchangeRateService(),
        )

        result = usecase.execute(user_id=request.user.ory_id)
        return Response(result, status=status.HTTP_200_OK)
