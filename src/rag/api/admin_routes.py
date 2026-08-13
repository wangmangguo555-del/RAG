from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from rag.api.dependencies import get_container, require_admin
from rag.api.schemas import (
    IndexRequest,
    JobResponse,
    RepositoryCreate,
    RepositoryResponse,
)
from rag.container import Container
from rag.domain.models import IndexJob, Repository

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


def _job_response(job: IndexJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        repo_id=job.repo_id,
        requested_ref=job.requested_ref,
        status=job.status.value,
        resolved_commit_sha=job.resolved_commit_sha,
        error_code=job.error_code,
        error_message=job.error_message,
    )


@router.post("/repos", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def register_repository(
    request: RepositoryCreate, container: Container = Depends(get_container)
) -> RepositoryResponse:
    repository = Repository(
        id=request.id,
        name=request.name,
        source_type=request.source_type,
        source_uri=request.source_uri,
        default_ref=request.default_ref,
        include=tuple(request.include),
        exclude=tuple(request.exclude),
    )
    await container.metadata.register_repository(repository)
    return RepositoryResponse(**request.model_dump(), enabled=True)


@router.get("/repos", response_model=list[RepositoryResponse])
async def list_repositories(
    container: Container = Depends(get_container),
) -> list[RepositoryResponse]:
    repositories = await container.metadata.list_repositories()
    return [
        RepositoryResponse(
            id=repo.id,
            name=repo.name,
            source_type=repo.source_type,
            source_uri=repo.source_uri,
            default_ref=repo.default_ref,
            include=list(repo.include),
            exclude=list(repo.exclude),
            enabled=repo.enabled,
        )
        for repo in repositories
    ]


@router.post("/repos/{repo_id}/index", response_model=JobResponse, status_code=202)
async def submit_index(
    repo_id: str,
    request: IndexRequest,
    container: Container = Depends(get_container),
) -> JobResponse:
    job_id = await container.index_service.submit(repo_id, request.ref)
    job = await container.metadata.get_job(job_id)
    assert job is not None
    return _job_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, container: Container = Depends(get_container)) -> JobResponse:
    job = await container.metadata.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_response(job)
