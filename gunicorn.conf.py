import multiprocessing

# Worker class — gevent provides cooperative green-thread concurrency.
# The ggevent worker calls gevent.monkey.patch_all() automatically before
# any application code is imported, so no manual monkey-patching is needed.
worker_class = "gevent"

# 2 OS-level worker processes. Concurrency within each worker comes from
# greenlets (worker_connections below), so fewer processes are needed than
# with sync workers. Adjust based on CPU count and load testing results.
workers = max(2, multiprocessing.cpu_count())

# Max simultaneous greenlet connections per worker process.
worker_connections = 1000

# Bind address — overridden by docker-compose command flag.
bind = "0.0.0.0:8000"

# Kill a worker that takes longer than this to handle a single request (seconds).
timeout = 120

# How long to wait for in-flight requests to finish on graceful shutdown.
graceful_timeout = 30

# Keep-alive timeout for persistent HTTP connections (seconds).
# Should be slightly above the load balancer's idle timeout.
keepalive = 5

# Recycle workers after this many requests to prevent unbounded memory growth.
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):
    """Initialize gRPC gevent integration after each worker forks.

    Ordering constraint (must be respected):
      1. gevent.monkey.patch_all()  — done automatically by the gevent worker class
                                      BEFORE this hook is called.
      2. grpc.experimental.gevent.init_gevent()  — called here, per-worker.
      3. grpc.insecure_channel(...)  — called lazily on first use inside the worker.

    Importing grpc inside this function body ensures the master process never
    loads the gRPC C-extension before forking, preventing stale file-descriptor
    inheritance across workers.
    """
    import grpc.experimental.gevent as grpc_gevent  # noqa: PLC0415

    grpc_gevent.init_gevent()

    # Signal the lazy channel module that init has run in this worker.
    try:
        from authentication.adapters.django import grpc_channel  # noqa: PLC0415

        grpc_channel.mark_gevent_initialized()
    except ImportError:
        pass  # gRPC adapter not yet installed — safe to ignore
