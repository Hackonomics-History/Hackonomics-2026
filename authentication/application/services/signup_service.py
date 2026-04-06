from types import SimpleNamespace

from authentication.adapters.django.adapter_factory import get_auth_adapter
from authentication.adapters.ports import AuthServiceAdapter
from common.errors.error_codes import ErrorCode
from common.errors.exceptions import BusinessException


class SignupService:
    def __init__(self) -> None:
        self.central_auth: AuthServiceAdapter = get_auth_adapter()

    def signup(self, email: str, password: str):
        """Proxy signup to the Go BFF. Returns a lightweight user object with ory_id."""
        try:
            result = self.central_auth.signup(email=email, password=password)
        except BusinessException:
            raise
        except Exception:
            raise BusinessException(ErrorCode.EXTERNAL_API_FAILED)

        return SimpleNamespace(
            ory_id=result.get("ory_id") or result.get("id"),
            email=result.get("email", email),
        )
