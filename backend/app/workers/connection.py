"""Shared Redis connection and RQ queue for workers."""

from redis import Redis
from rq import Queue

from app.config import settings

redis_conn = Redis.from_url(settings.redis_url)
task_queue = Queue("jobtracker", connection=redis_conn)
