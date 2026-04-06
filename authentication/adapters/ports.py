"""Adapter port (Protocol) for the Central-Auth service.

Both ``CentralAuthAdapter`` (HTTP) and ``GrpcAuthAdapter`` satisfy this Protocol
via structural subtyping — no inheritance required.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AuthServiceAdapter(Protocol):
    """Interface that every Central-Auth adapter must satisfy."""

    def login(
        self,
        email: str,
        password: str,
        device_id: str,
        remember_me: bool,
    ) -> dict:
        """Authenticate with email + password. Returns ``{"access_token", "refresh_token"}``."""
        ...

    def signup(self, email: str, password: str) -> dict:
        """Create a new identity. Returns ``{"ory_id", "email"}``."""
        ...

    def google_login(self, email: str, device_id: str) -> dict:
        """Issue tokens for a Google-verified email. Returns ``{"access_token", "refresh_token"}``."""
        ...

    def refresh(self, refresh_token: str) -> dict:
        """Rotate refresh token. Returns ``{"access_token", "refresh_token"}``."""
        ...

    def logout(self, refresh_token: str) -> None:
        """Invalidate the session identified by the refresh token."""
        ...
