"""Shared test fixtures and helpers."""
import grpc


class FakeRpcError(grpc.RpcError):
    """Concrete grpc.RpcError subclass for testing.

    grpc.RpcError is abstract and ``code()`` / ``details()`` live on grpc.Call.
    Using MagicMock(spec=grpc.RpcError) fails because spec doesn't include those
    methods.  This concrete class is the canonical way to fake gRPC errors in tests.
    """

    def __init__(self, code: grpc.StatusCode, detail: str = "") -> None:
        self._code = code
        self._detail = detail

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._detail
