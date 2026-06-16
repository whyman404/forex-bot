"""Email worker — drains Redis `email_queue` and sends via active provider.

Run with:  python -m app.workers.email_worker

Atlas Goro — simple polling loop using BRPOP (blocking pop). One process is
enough for MVP; horizontally scale by running more replicas if needed.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.email_service import render_and_send_now

logger = get_logger(__name__)


async def _process_one(job: dict[str, Any]) -> None:
    to = job.get("to")
    template = job.get("template")
    context = job.get("context") or {}
    if not to or not template:
        logger.warning("email_job_malformed", job=job)
        return
    try:
        await render_and_send_now(to=to, template=template, context=context)
        logger.info("email_sent", to=to, template=template)
    except Exception as exc:  # noqa: BLE001
        logger.error("email_send_failed", to=to, template=template, err=str(exc))


async def run() -> int:
    configure_logging()
    settings = get_settings()
    try:
        from redis.asyncio import Redis
    except Exception as exc:  # noqa: BLE001
        logger.error("redis_unavailable", err=str(exc))
        return 1

    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    queue_name = settings.email_queue_name
    stop = asyncio.Event()

    def _stop(*_: Any) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    logger.info("email_worker_started", queue=queue_name)
    while not stop.is_set():
        try:
            item = await redis.brpop(queue_name, timeout=2)
            if item is None:
                continue
            _, raw = item
            try:
                job = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("email_job_bad_json", err=str(exc))
                continue
            await _process_one(job)
        except Exception as exc:  # noqa: BLE001
            logger.error("email_worker_loop_error", err=str(exc))
            await asyncio.sleep(1)

    await redis.aclose()
    logger.info("email_worker_stopped")
    return 0


def main() -> int:
    """Procfile-friendly entrypoint.

    Usage on Railway:
        Procfile: email-worker: python -m app.workers.email_worker
    """
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
