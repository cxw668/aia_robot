from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, JobStatus, KnowledgeIngestJob
from app.knowledge_base.ingestion.pipeline import ingest_directory, ingest_file

_UNSET = object()
_WORKER_POLL_INTERVAL_SECONDS = 2.0
_worker_task: asyncio.Task[None] | None = None
_worker_stop_event: asyncio.Event | None = None
_worker_wakeup_event: asyncio.Event | None = None


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


async def get_ingest_job(db: AsyncSession, job_id: str) -> KnowledgeIngestJob | None:
    result = await db.execute(
        select(KnowledgeIngestJob).where(KnowledgeIngestJob.id == job_id)
    )
    return result.scalar_one_or_none()


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


async def claim_next_pending_ingest_job() -> KnowledgeIngestJob | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(KnowledgeIngestJob)
            .where(KnowledgeIngestJob.status == JobStatus.PENDING)
            .order_by(KnowledgeIngestJob.created_at.asc(), KnowledgeIngestJob.id.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.finished_at = None
        job.error = None
        await db.commit()
        await db.refresh(job)
        return job


async def requeue_ingest_job(job_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(KnowledgeIngestJob)
            .where(
                KnowledgeIngestJob.id == job_id,
                KnowledgeIngestJob.status == JobStatus.FAILED,
            )
            .values(
                status=JobStatus.PENDING,
                doc_count=0,
                schema_name=None,
                skipped_count=0,
                failed_items=0,
                error="Job manually requeued.",
                started_at=None,
                finished_at=None,
            )
        )
        await db.commit()
        return bool(result.rowcount)


def can_retry_ingest_job(job: KnowledgeIngestJob) -> tuple[bool, str | None]:
    if job.status != JobStatus.FAILED:
        return False, "Only failed jobs can be retried"
    if job.job_type == "file" and (not job.source or not os.path.exists(job.source)):
        return False, "Uploaded file is no longer available for retry"
    return True, None


async def recover_interrupted_ingest_jobs() -> int:
    async with AsyncSessionLocal() as db:
        stmt = (
            update(KnowledgeIngestJob)
            .where(KnowledgeIngestJob.status == JobStatus.RUNNING)
            .values(
                status=JobStatus.PENDING,
                doc_count=0,
                schema_name=None,
                skipped_count=0,
                failed_items=0,
                error="Job recovered after service restart and queued for retry.",
                started_at=None,
                finished_at=None,
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return int(result.rowcount or 0)


def notify_ingest_worker() -> None:
    if _worker_wakeup_event is not None:
        _worker_wakeup_event.set()


async def start_ingest_worker() -> None:
    global _worker_task, _worker_stop_event, _worker_wakeup_event
    if _worker_task is not None and not _worker_task.done():
        return

    _worker_stop_event = asyncio.Event()
    _worker_wakeup_event = asyncio.Event()
    _worker_task = asyncio.create_task(_ingest_worker_loop(), name="knowledge-ingest-worker")
    notify_ingest_worker()


async def stop_ingest_worker() -> None:
    global _worker_task, _worker_stop_event, _worker_wakeup_event
    if _worker_task is None:
        return

    if _worker_stop_event is not None:
        _worker_stop_event.set()
    if _worker_wakeup_event is not None:
        _worker_wakeup_event.set()

    try:
        await _worker_task
    finally:
        _worker_task = None
        _worker_stop_event = None
        _worker_wakeup_event = None


async def _ingest_worker_loop() -> None:
    stop_event = _worker_stop_event
    wakeup_event = _worker_wakeup_event
    if stop_event is None or wakeup_event is None:
        return

    while not stop_event.is_set():
        job = await claim_next_pending_ingest_job()
        if job is None:
            try:
                await asyncio.wait_for(wakeup_event.wait(), timeout=_WORKER_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
            wakeup_event.clear()
            continue

        await _process_ingest_job(job)


async def _process_ingest_job(job: KnowledgeIngestJob) -> None:
    try:
        result = await asyncio.to_thread(_execute_ingest_job, job)
        summary = summarize_job_result(result)
        await update_ingest_job(
            job.id,
            status=JobStatus.DONE,
            doc_count=summary["doc_count"],
            schema_name=summary["schema_name"],
            skipped_count=summary["skipped_count"],
            failed_items=summary["failed_items"],
            error=summary["error"],
            finished_at=datetime.utcnow(),
        )
        _cleanup_completed_job_source(job)
    except Exception as exc:
        await update_ingest_job(
            job.id,
            status=JobStatus.FAILED,
            error=str(exc),
            finished_at=datetime.utcnow(),
        )


def _execute_ingest_job(job: KnowledgeIngestJob) -> dict | list[dict]:
    if job.job_type == "dir":
        return ingest_directory(job.source, collection_name=job.collection_name)
    if job.job_type in {"file", "forms_pdf"}:
        return ingest_file(job.source, collection_name=job.collection_name)
    if job.job_type == "url":
        return _ingest_url_source(job.source, job.collection_name)
    raise RuntimeError(f"Unsupported ingest job type: {job.job_type}")


def _ingest_url_source(url: str, collection_name: str) -> dict | list[dict]:
    tmp_path = ""
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        suffix = os.path.splitext(url.split("?", 1)[0])[1] or ".json"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(response.content)
            tmp_path = handle.name
        return ingest_file(tmp_path, collection_name=collection_name)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _cleanup_completed_job_source(job: KnowledgeIngestJob) -> None:
    if job.job_type != "file" or not job.source:
        return
    try:
        os.unlink(job.source)
    except OSError:
        pass
