from authentication.adapters.django.adapter_factory import get_auth_adapter
from authentication.adapters.ports import AuthServiceAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class LogoutService:
    def __init__(self):
        self.central_auth: AuthServiceAdapter = get_auth_adapter()

    def logout(self, refresh_token: str) -> None:
        if not refresh_token:
            raise BusinessException(ErrorCode.REFRESH_TOKEN_MISSING)

        try:
            self.central_auth.logout(refresh_token)
        except Exception:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
