from typing import Dict

from authentication.adapters.django.auth_service import CentralAuthAdapter
from authentication.adapters.django.google_oauth import GoogleOAuthAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class OAuthService:
    def __init__(self) -> None:
        self.google_adapter = GoogleOAuthAdapter()
        self.central_auth = CentralAuthAdapter()

    def google_login(self, code: str) -> Dict[str, str]:
        try:
            token_data = self.google_adapter.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            if not access_token:
                raise BusinessException(ErrorCode.GOOGLE_AUTH_FAILED)

            userinfo = self.google_adapter.get_userinfo(access_token)
        except BusinessException:
            raise
        except Exception:
            raise BusinessException(ErrorCode.GOOGLE_AUTH_FAILED)

        email = userinfo.get("email") if isinstance(userinfo, dict) else None
        if not email:
            raise BusinessException(ErrorCode.INVALID_PARAMETER)

        # Delegate token issuance to the BFF; no local user creation
        try:
            return self.central_auth.google_login(email=email, device_id="google-oauth")
        except BusinessException:
            raise
        except Exception:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
