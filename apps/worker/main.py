"""
RQ Worker Entry Point

Run with: rq worker --path /path/to/apps/worker
"""
import os
import sys
from pathlib import Path

# Add paths for imports
WORKER_DIR = Path(__file__).resolve().parent
API_DIR = WORKER_DIR.parent / "api"
sys.path.insert(0, str(WORKER_DIR))
sys.path.insert(0, str(API_DIR))

from redis import Redis
from rq import Worker, Queue

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

if __name__ == "__main__":
    redis_conn = Redis.from_url(REDIS_URL)
    queues = [Queue("default", connection=redis_conn)]
    
    worker = Worker(queues, connection=redis_conn)
    worker.work()
