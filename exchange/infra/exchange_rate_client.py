import logging

import requests
from requests.exceptions import RequestException, Timeout

logger = logging.getLogger(__name__)


class ExchangeRateClient:
    BASE_URL = "https://api.frankfurter.app/latest"

    def get_rate(self, target_currency: str, base: str = "USD") -> float:
        params = {
            "from": base,
            "to": target_currency,
        }

        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=5,
            )

            response.raise_for_status()
            data = response.json()

            return data["rates"][target_currency]

        except Timeout:
            logger.warning("Exchange API timeout")
            return self._fallback_rate(target_currency)

        except RequestException as e:
            logger.exception("Exchange API request failed: %s", e)
            return self._fallback_rate(target_currency)

        except Exception as e:
            logger.exception("Unexpected exchange error: %s", e)
            return self._fallback_rate(target_currency)

    def _fallback_rate(self, currency: str) -> float:
        return 0.0
