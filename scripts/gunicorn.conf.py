"""Gunicorn configuration for production.

Invoked by systemd as::

    gunicorn app.main:app --config scripts/gunicorn.conf.py
"""

from __future__ import annotations

import multiprocessing
import os

bind = f"{os.environ.get('HTTP_HOST', '127.0.0.1')}:{os.environ.get('HTTP_PORT', '8000')}"

workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 60
graceful_timeout = 30
keepalive = 5

max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# structlog owns log formatting — keep gunicorn's format minimal.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'

proc_name = "softtarget"
