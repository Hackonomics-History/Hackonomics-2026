"""Factory that returns the active Central-Auth adapter.

Toggle via ``CENTRAL_AUTH_USE_GRPC`` Django setting (default: ``False``).

The gRPC adapter is imported lazily so that ``grpcio`` modules are never loaded
when the HTTP path is active — important for environments where grpcio is not
installed or where gevent has not yet been initialized.
"""

from django.conf import settings

from authentication.adapters.ports import AuthServiceAdapter


def get_auth_adapter() -> AuthServiceAdapter:
    """Return the configured Central-Auth adapter.

    Returns
    -------
    GrpcAuthAdapter  when ``settings.CENTRAL_AUTH_USE_GRPC`` is ``True``.
    CentralAuthAdapter  otherwise (default HTTP path).
    """
    if getattr(settings, "CENTRAL_AUTH_USE_GRPC", False):
        from authentication.adapters.django.grpc_auth_service import (  # noqa: PLC0415
            GrpcAuthAdapter,
        )

        return GrpcAuthAdapter()

    from authentication.adapters.django.auth_service import (  # noqa: PLC0415
        CentralAuthAdapter,
    )

    return CentralAuthAdapter()
