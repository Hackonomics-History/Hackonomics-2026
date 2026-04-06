from authentication.adapters.django.adapter_factory import get_auth_adapter
from authentication.adapters.ports import AuthServiceAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class LoginService:
    def __init__(self) -> None:
        self.central_auth: AuthServiceAdapter = get_auth_adapter()

    def login(self, email: str, password: str, device_id: str, remember_me: bool) -> dict:
        """Proxy credentials to the Go BFF. Django no longer owns user auth."""
        try:
            return self.central_auth.login(
                email=email,
                password=password,
                device_id=device_id,
                remember_me=remember_me,
            )
        except BusinessException:
            raise
        except Exception:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)
