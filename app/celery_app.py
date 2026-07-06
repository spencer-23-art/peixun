from celery import Celery
from .config import REDIS_URL

celery_app = Celery(
    "ocr_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    worker_concurrency=2,  # 2核限制，设置 concurrency 为 2
    broker_transport_options={"protocol": 2},
    redis_backend_transport_options={"protocol": 2},
)
