from authentication.adapters.django.adapter_factory import get_auth_adapter
from authentication.adapters.ports import AuthServiceAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class RefreshService:
    def __init__(self):
        self.central_auth: AuthServiceAdapter = get_auth_adapter()

    def refresh(self, refresh_token: str) -> dict:
        if not refresh_token:
            raise BusinessException(ErrorCode.REFRESH_TOKEN_MISSING)

        try:
            return self.central_auth.refresh(refresh_token)
        except Exception:
            raise BusinessException(ErrorCode.REFRESH_TOKEN_INVALID)
