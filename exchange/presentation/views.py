from datetime import date

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.EmptySerializer import EmptySerializer
from exchange.application.services import ExchangeHistoryService, ExchangeRateService
from exchange.presentation.serializers import ExchangeRateResponseSerializer


class UsdToCurrencyAPIView(GenericAPIView):
    serializer_class = ExchangeRateResponseSerializer
    permission_classes = [AllowAny]

    def get(self, request, currency: str):
        service = ExchangeRateService()
        rate = service.get_usd_to_currency(currency.upper())

        data = {
            "base": "USD",
            "target": currency.upper(),
            "rate": rate,
        }

        serializer = self.get_serializer(instance=data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ExchangeHistoryAPIView(GenericAPIView):
    serializer_class = EmptySerializer
    permission_classes = [AllowAny]

    def get(self, request):
        currency = request.query_params.get("currency")
        period = request.query_params.get("period", "6m")

        history = ExchangeHistoryService().get_usd_history_until_today(
            currency=currency.upper() if currency else None,
            period=period,
        )
        return Response(
            {
                "base": "USD",
                "target": currency.upper() if currency else ExchangeHistoryService.DEFAULT_CURRENCY,
                "period": period,
                "end_date": str(date.today()),
                "history": history,
            },
            status=status.HTTP_200_OK,
        )
