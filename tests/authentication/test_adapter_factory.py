"""Tests for the adapter factory toggle."""
import pytest
from unittest.mock import patch

from authentication.adapters.ports import AuthServiceAdapter


class TestAdapterFactory:
    def test_returns_http_adapter_by_default(self, settings):
        settings.CENTRAL_AUTH_USE_GRPC = False

        from authentication.adapters.django.adapter_factory import get_auth_adapter
        from authentication.adapters.django.auth_service import CentralAuthAdapter

        adapter = get_auth_adapter()
        assert isinstance(adapter, CentralAuthAdapter)

    def test_returns_grpc_adapter_when_flag_true(self, settings):
        settings.CENTRAL_AUTH_USE_GRPC = True
        # grpc_channel.get_channel() must not be called at construction time.
        with patch(
            "authentication.adapters.django.grpc_channel.get_channel"
        ) as mock_channel:
            mock_channel.return_value = object()
            from authentication.adapters.django.adapter_factory import get_auth_adapter
            from authentication.adapters.django.grpc_auth_service import GrpcAuthAdapter

            adapter = get_auth_adapter()
            assert isinstance(adapter, GrpcAuthAdapter)
            # Channel must NOT have been called at construction time — lazy only.
            mock_channel.assert_not_called()

    def test_both_adapters_satisfy_protocol(self, settings):
        settings.CENTRAL_AUTH_USE_GRPC = False
        from authentication.adapters.django.adapter_factory import get_auth_adapter

        http_adapter = get_auth_adapter()
        assert isinstance(http_adapter, AuthServiceAdapter)

        settings.CENTRAL_AUTH_USE_GRPC = True
        with patch("authentication.adapters.django.grpc_channel.get_channel"):
            grpc_adapter = get_auth_adapter()
            assert isinstance(grpc_adapter, AuthServiceAdapter)
