from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog

from rag.container import Container
from rag.infrastructure.settings import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def run_worker(*, once: bool = False) -> None:
    config_path = os.getenv("RAG_CONFIG", str(PROJECT_ROOT / "config" / "default.yaml"))
    container = Container.build(load_settings(config_path), PROJECT_ROOT)
    await container.metadata.initialize()
    log = structlog.get_logger()
    try:
        while True:
            job = await container.metadata.claim_next_job()
            if not job:
                if once:
                    return
                await asyncio.sleep(container.settings.ingestion.worker_poll_seconds)
                continue
            try:
                stats = await container.index_service.execute_job(job.id)
                log.info("index_job_succeeded", job_id=job.id, repo_id=job.repo_id, **stats)
            except Exception as exc:
                log.exception(
                    "index_job_failed", job_id=job.id, repo_id=job.repo_id, error=str(exc)
                )
            if once:
                return
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
