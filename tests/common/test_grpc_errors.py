"""Tests for gRPC error classification helpers."""
import grpc
import pytest

from common.resilience.grpc_errors import is_grpc_infrastructure_error, is_grpc_retryable
from tests.conftest import FakeRpcError


def _rpc_error(code: grpc.StatusCode) -> grpc.RpcError:
    return FakeRpcError(code)


class TestIsGrpcInfrastructureError:
    @pytest.mark.parametrize("code", [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    ])
    def test_returns_true_for_infrastructure_codes(self, code):
        assert is_grpc_infrastructure_error(_rpc_error(code)) is True

    @pytest.mark.parametrize("code", [
        grpc.StatusCode.UNAUTHENTICATED,
        grpc.StatusCode.ALREADY_EXISTS,
        grpc.StatusCode.INVALID_ARGUMENT,
        grpc.StatusCode.NOT_FOUND,
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.OK,
        grpc.StatusCode.INTERNAL,
    ])
    def test_returns_false_for_non_infrastructure_codes(self, code):
        assert is_grpc_infrastructure_error(_rpc_error(code)) is False

    def test_returns_false_for_non_grpc_exception(self):
        assert is_grpc_infrastructure_error(ValueError("boom")) is False

    def test_returns_false_for_plain_exception(self):
        assert is_grpc_infrastructure_error(RuntimeError()) is False


class TestIsGrpcRetryable:
    def test_is_alias_for_infrastructure_error(self):
        assert is_grpc_retryable(_rpc_error(grpc.StatusCode.UNAVAILABLE)) is True
        assert is_grpc_retryable(_rpc_error(grpc.StatusCode.UNAUTHENTICATED)) is False
