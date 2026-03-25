from rest_framework.authentication import BaseAuthentication


class JWTAuthentication(BaseAuthentication):
    """Deprecated no-op shim. Authentication is now handled by JWKSMiddleware.

    This class is kept so that any stale references to it do not cause import
    errors, but it is no longer listed in DEFAULT_AUTHENTICATION_CLASSES and
    will never be invoked by DRF.
    """

    def authenticate(self, request):
        return None

    def authenticate_header(self, request):
        return "Bearer"
