"""Per-worker lazy gRPC channel singleton.

The channel must be created AFTER ``grpc.experimental.gevent.init_gevent()``
runs in Gunicorn's ``post_fork`` hook.  It must NEVER be created at import time
or in the master process.

Usage
-----
    from authentication.adapters.django.grpc_channel import get_channel
    stub = AuthServiceStub(get_channel())
"""

import logging
from typing import Optional

import grpc
from django.conf import settings

logger = logging.getLogger(__name__)

# Set to True by post_fork via mark_gevent_initialized().
# Prevents accidental channel creation before gevent is patched.
_gevent_initialized: bool = False

_channel: Optional[grpc.Channel] = None


def mark_gevent_initialized() -> None:
    """Called by gunicorn.conf.py post_fork hook after init_gevent()."""
    global _gevent_initialized
    _gevent_initialized = True


def get_channel() -> grpc.Channel:
    """Return (or create) the per-worker insecure gRPC channel.

    Raises
    ------
    RuntimeError
        If called before ``mark_gevent_initialized()`` has been invoked — i.e.
        before the Gunicorn post_fork hook has run.  This prevents silent
        deadlocks caused by using gRPC's C-core without gevent patching.
    """
    global _channel

    if not _gevent_initialized:
        raise RuntimeError(
            "gRPC channel requested before gevent was initialized. "
            "Ensure grpc.experimental.gevent.init_gevent() is called in the "
            "Gunicorn post_fork hook before any gRPC call is made."
        )

    if _channel is None:
        target = getattr(settings, "CENTRAL_AUTH_GRPC_TARGET", "auth-server:50051")
        _channel = grpc.insecure_channel(
            target,
            options=[
                # Send keepalive pings every 10 s so idle channels don't silently
                # break when Docker networking drops the TCP connection.
                ("grpc.keepalive_time_ms", 10_000),
                ("grpc.keepalive_timeout_ms", 5_000),
                ("grpc.keepalive_permit_without_calls", 1),
                # Reconnect quickly after transient failures.
                ("grpc.initial_reconnect_backoff_ms", 500),
                ("grpc.max_reconnect_backoff_ms", 5_000),
            ],
        )
        logger.info("[gRPC] Channel created → %s", target)

    return _channel
