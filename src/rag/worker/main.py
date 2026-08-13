from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from rag.container import Container
from rag.domain.errors import RagError
from rag.infrastructure.settings import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def _heartbeat_job(container: Container, job_id: str, stopped: asyncio.Event) -> None:
    """索引期间持续刷新心跳，区分耗时任务与已经失联的 Worker。"""

    interval = container.settings.ingestion.worker_heartbeat_seconds
    while not stopped.is_set():
        try:
            await asyncio.wait_for(stopped.wait(), timeout=interval)
        except TimeoutError:
            try:
                await container.metadata.heartbeat_job(job_id)
            except Exception as exc:  # noqa: BLE001 - 心跳失败不能遮蔽主索引任务的真实结果
                structlog.get_logger().warning(
                    "index_job_heartbeat_failed", job_id=job_id, error=str(exc)
                )


async def _execute_claimed_job(container: Container, job_id: str, repo_id: str) -> None:
    log = structlog.get_logger()
    stopped = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_job(container, job_id, stopped))
    try:
        stats = await container.index_service.execute_job(job_id)
        log.info("index_job_succeeded", job_id=job_id, repo_id=repo_id, **stats)
    except Exception as exc:
        retryable = isinstance(exc, RagError) and exc.retryable
        job = await container.metadata.get_job(job_id)
        attempt = job.attempt if job else 1
        # 退避随尝试次数增长，避免本地模型离线时 Worker 持续占用 CPU 和日志。
        retry_delay = container.settings.ingestion.job_retry_base_seconds * 2 ** max(
            0, attempt - 1
        )
        status = await container.metadata.retry_or_fail_job(
            job_id,
            retryable=retryable,
            max_attempts=container.settings.ingestion.job_max_attempts,
            retry_delay_seconds=retry_delay,
            error_code=getattr(exc, "code", "INDEXING_ERROR"),
            error_message=str(exc),
        )
        log.exception(
            "index_job_failed",
            job_id=job_id,
            repo_id=repo_id,
            retryable=retryable,
            next_status=status,
            error=str(exc),
        )
    finally:
        stopped.set()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_worker(*, once: bool = False) -> None:
    config_path = os.getenv("RAG_CONFIG", str(PROJECT_ROOT / "config" / "default.yaml"))
    container = Container.build(load_settings(config_path), PROJECT_ROOT)
    await container.metadata.initialize()
    log = structlog.get_logger()
    try:
        stale_before = (
            datetime.now(UTC)
            - timedelta(seconds=container.settings.ingestion.job_stale_after_seconds)
        ).isoformat()
        recovery = await container.metadata.recover_stale_jobs(
            stale_before, container.settings.ingestion.job_max_attempts
        )
        if any(recovery.values()):
            log.info("stale_index_jobs_recovered", **recovery)
        while True:
            job = await container.metadata.claim_next_job()
            if not job:
                if once:
                    return
                await asyncio.sleep(container.settings.ingestion.worker_poll_seconds)
                continue
            await _execute_claimed_job(container, job.id, job.repo_id)
            if once:
                return
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
