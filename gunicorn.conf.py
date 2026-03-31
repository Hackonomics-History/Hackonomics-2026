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
