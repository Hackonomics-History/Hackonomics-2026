from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.adapters.orm.repository import DjangoAccountRepository
from exchange.application.services import ExchangeHistoryService
from simulation.application.usecases.compare_investment_usecase import (
    CompareInvestmentUseCase,
)
from simulation.presentation.serializers import CompareSimulationRequestSerializer


class CompareDcaVsDepositAPIView(GenericAPIView):
    serializer_class = CompareSimulationRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user = request.user

        usecase = CompareInvestmentUseCase(
            account_repository=DjangoAccountRepository(),
            exchange_history_service=ExchangeHistoryService(),
        )

        result = usecase.execute(
            user_id=user.ory_id,
            period=data.get("period", "1y"),
            deposit_rate=data.get("deposit_rate"),
        )

        return Response(result.to_dict(), status=status.HTTP_200_OK)
