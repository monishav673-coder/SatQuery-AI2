"""
SATQUERY AI — RQ Worker Entry-Point
Run with:  python worker/worker_main.py
Or via Docker:  CMD ["python", "worker/worker_main.py"]
"""

import logging
import os
import sys

# Make backend importable
_backend = os.path.join(os.path.dirname(__file__), "..", "backend")
_root    = os.path.join(os.path.dirname(__file__), "..")
for p in (_backend, _root):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("satquery.worker")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUES    = os.environ.get("RQ_QUEUES", "analysis,default").split(",")


def main() -> None:
    try:
        import redis as redis_lib
        from rq import Worker, Queue, Connection
    except ImportError:
        logger.critical(
            "rq and redis packages are required. "
            "Install: pip install rq redis"
        )
        sys.exit(1)

    try:
        conn = redis_lib.from_url(REDIS_URL)
        conn.ping()
        logger.info("Connected to Redis at %s", REDIS_URL)
    except Exception as exc:
        logger.critical("Cannot connect to Redis at %s: %s", REDIS_URL, exc)
        sys.exit(1)

    logger.info("Starting RQ worker. Queues: %s", QUEUES)
    with Connection(conn):
        worker = Worker(list(map(Queue, QUEUES)))
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
