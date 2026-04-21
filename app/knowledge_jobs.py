from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, JobStatus, KnowledgeIngestJob

_UNSET = object()


def summarize_job_result(result: dict | list[dict]) -> dict:
    if isinstance(result, list):
        doc_count = sum(int(item.get("doc_count", 0) or 0) for item in result)
        non_error_schemas = {
            str(item.get("schema") or "")
            for item in result
            if item.get("schema") and item.get("schema") != "error"
        }
        failed_items = sum(1 for item in result if item.get("schema") == "error")
        errors = [str(item.get("error")) for item in result if item.get("error")]
        schema_name = ""
        if len(non_error_schemas) == 1:
            schema_name = next(iter(non_error_schemas))
        elif len(non_error_schemas) > 1:
            schema_name = "mixed"
        return {
            "doc_count": doc_count,
            "schema_name": schema_name,
            "skipped_count": 0,
            "failed_items": failed_items,
            "error": "; ".join(errors[:3]) if errors else None,
        }

    return {
        "doc_count": int(result.get("doc_count", 0) or 0),
        "schema_name": str(result.get("schema") or ""),
        "skipped_count": int(result.get("skipped", 0) or 0),
        "failed_items": int(result.get("failed", 0) or result.get("failed_items", 0) or 0),
        "error": result.get("error"),
    }


def serialize_ingest_job(job: KnowledgeIngestJob) -> dict:
    return {
        "job_id": job.id,
        "type": job.job_type,
        "source": job.source,
        "collection": job.collection_name,
        "status": job.status.value,
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "doc_count": job.doc_count,
        "schema": job.schema_name or "",
        "skipped": job.skipped_count,
        "failed_items": job.failed_items,
        "error": job.error,
    }


async def create_ingest_job(
    db: AsyncSession,
    *,
    job_id: str,
    job_type: str,
    source: str,
    collection_name: str,
    requested_by: int | None = None,
) -> KnowledgeIngestJob:
    job = KnowledgeIngestJob(
        id=job_id,
        job_type=job_type,
        source=source,
        collection_name=collection_name,
        requested_by=requested_by,
    )
    db.add(job)
    await db.flush()
    return job


async def list_ingest_jobs(db: AsyncSession, *, limit: int = 200) -> list[KnowledgeIngestJob]:
    stmt = (
        select(KnowledgeIngestJob)
        .order_by(KnowledgeIngestJob.created_at.desc(), KnowledgeIngestJob.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_ingest_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    doc_count: int | None = None,
    schema_name: str | None = None,
    skipped_count: int | None = None,
    failed_items: int | None = None,
    error: str | None | object = _UNSET,
    started_at: datetime | None | object = _UNSET,
    finished_at: datetime | None | object = _UNSET,
) -> None:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if doc_count is not None:
        values["doc_count"] = doc_count
    if schema_name is not None:
        values["schema_name"] = schema_name
    if skipped_count is not None:
        values["skipped_count"] = skipped_count
    if failed_items is not None:
        values["failed_items"] = failed_items
    if error is not _UNSET:
        values["error"] = error
    if started_at is not _UNSET:
        values["started_at"] = started_at
    if finished_at is not _UNSET:
        values["finished_at"] = finished_at
    if not values:
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(KnowledgeIngestJob)
            .where(KnowledgeIngestJob.id == job_id)
            .values(**values)
        )
        await db.commit()


async def recover_interrupted_ingest_jobs() -> int:
    async with AsyncSessionLocal() as db:
        stmt = (
            update(KnowledgeIngestJob)
            .where(KnowledgeIngestJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
            .values(
                status=JobStatus.FAILED,
                error="Job interrupted by service restart.",
                finished_at=datetime.utcnow(),
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return int(result.rowcount or 0)
