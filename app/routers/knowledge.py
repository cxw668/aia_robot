"""Knowledge base router — multi-collection architecture.

Endpoints
---------
POST   /kb/ingest                submit ingest job (dir | url)
POST   /kb/upload                file upload ingest
GET    /kb/jobs                  list ingest jobs
GET    /kb/collections           list all Qdrant collections with doc counts
DELETE /kb/collections/{name}    delete an entire collection
GET    /kb/docs                  list / search documents
DELETE /kb/docs/{doc_id}         delete a single document
GET    /health                   Qdrant status
"""
from __future__ import annotations

import os
import tempfile
import time
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from qdrant_client import models
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import JobStatus, get_db
from app.knowledge_base.config import DEFAULT_COLLECTION
from app.knowledge_base.core import get_client, get_model
from app.knowledge_jobs import (
    can_retry_ingest_job,
    create_ingest_job,
    get_ingest_job,
    list_ingest_jobs,
    notify_ingest_worker,
    requeue_ingest_job,
    serialize_ingest_job,
)

router = APIRouter(tags=["knowledge"])


class IngestJob(BaseModel):
    job_id: str
    type: str
    source: str
    collection: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    doc_count: int = 0
    # 使用 `schema_` 避免与 BaseModel.schema() 方法冲突，外部仍使用 key `schema`
    schema_: str = Field("", alias="schema")
    skipped: int = 0
    failed_items: int = 0
    error: str | None = None

    class Config:
        validate_by_name = True

class IngestRequest(BaseModel):
    type: str
    path: str | None = None
    url: str | None = None
    collection: str = DEFAULT_COLLECTION


def _save_uploaded_file(file: UploadFile, contents: bytes) -> str:
    upload_dir = os.path.join(tempfile.gettempdir(), "aia_robot_ingest")
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = os.path.basename(file.filename or "upload.json")
    suffix = os.path.splitext(safe_name)[1] or ".json"
    tmp_path = os.path.join(upload_dir, f"{uuid.uuid4().hex[:8]}_{safe_name}")
    if not tmp_path.endswith(suffix):
        tmp_path = f"{tmp_path}{suffix}"
    with open(tmp_path, "wb") as handle:
        handle.write(contents)
    return tmp_path


@router.post("/kb/ingest", status_code=202)
async def ingest(req: IngestRequest, db: AsyncSession = Depends(get_db)) -> dict:
    job_id = str(uuid.uuid4())[:8]

    if req.type == "dir":
        if not req.path:
            raise HTTPException(400, "path required")
        await create_ingest_job(
            db,
            job_id=job_id,
            job_type="dir",
            source=req.path,
            collection_name=req.collection,
        )
    elif req.type == "url":
        if not req.url:
            raise HTTPException(400, "url required")
        await create_ingest_job(
            db,
            job_id=job_id,
            job_type="url",
            source=req.url,
            collection_name=req.collection,
        )
    elif req.type == "forms_pdf":
        if not req.path:
            raise HTTPException(400, "path required for forms_pdf type")
        await create_ingest_job(
            db,
            job_id=job_id,
            job_type="forms_pdf",
            source=req.path,
            collection_name=req.collection,
        )
    else:
        raise HTTPException(400, f"unknown type: {req.type!r}  (supported: dir, url, forms_pdf)")

    await db.commit()
    notify_ingest_worker()
    return {"job_id": job_id, "collection": req.collection}


@router.post("/kb/upload", status_code=202)
async def upload_file(
    file: UploadFile = File(...),
    collection: str = Query(DEFAULT_COLLECTION, description="Target collection (category) name"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a JSON file and ingest it into the specified collection."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only .json files are supported")

    contents = await file.read()
    tmp_path = _save_uploaded_file(file, contents)

    job_id = str(uuid.uuid4())[:8]
    await create_ingest_job(
        db,
        job_id=job_id,
        job_type="file",
        source=tmp_path,
        collection_name=collection,
    )
    await db.commit()
    notify_ingest_worker()
    return {"job_id": job_id, "collection": collection}


@router.get("/kb/jobs", response_model=list[IngestJob])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[dict]:
    jobs = await list_ingest_jobs(db)
    return [serialize_ingest_job(job) for job in jobs]


@router.post("/kb/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    job = await get_ingest_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    can_retry, message = can_retry_ingest_job(job)
    if not can_retry:
        raise HTTPException(409, message or "Job cannot be retried")

    requeued = await requeue_ingest_job(job_id)
    if not requeued:
        raise HTTPException(409, "Job cannot be retried")

    notify_ingest_worker()
    return {"job_id": job_id, "status": JobStatus.PENDING.value}


@router.get("/kb/collections")
async def list_collections() -> dict:
    """List all Qdrant collections with their document counts."""
    client = get_client()
    try:
        cols = client.get_collections().collections
        result = []
        for collection in cols:
            try:
                info = client.get_collection(collection.name)
                result.append({"name": collection.name, "doc_count": info.points_count or 0})
            except Exception:
                result.append({"name": collection.name, "doc_count": 0})
        return {"collections": result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.delete("/kb/collections/{collection_name}")
async def delete_collection(collection_name: str) -> dict:
    """Delete an entire collection (knowledge base category)."""
    client = get_client()
    try:
        client.delete_collection(collection_name)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"deleted": collection_name}


@router.get("/kb/docs")
async def list_docs(
    collection: str = Query(DEFAULT_COLLECTION, description="Collection (category) name"),
    q: str | None = Query(None, description="Search query"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List or search documents in a specific collection."""
    client = get_client()
    existing = [item.name for item in client.get_collections().collections]
    if collection not in existing:
        return {"total": 0, "offset": offset, "limit": limit, "docs": [], "collection": collection}
    try:
        if q and q.strip():
            model = get_model()
            vec = model.encode(q, normalize_embeddings=True).tolist()
            hits = client.query_points(
                collection_name=collection,
                query=vec,
                limit=1000,
                with_payload=True,
            ).points
            all_docs = [{"id": str(hit.id), "score": round(hit.score, 4), **hit.payload} for hit in hits]
        else:
            result, _ = client.scroll(
                collection_name=collection,
                limit=1000,
                offset=0,
                with_payload=True,
                with_vectors=False,
            )
            all_docs = [{"id": str(point.id), "score": None, **point.payload} for point in result]
        total = len(all_docs)
        docs = all_docs[offset: offset + limit]
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"total": total, "offset": offset, "limit": limit, "docs": docs, "collection": collection}


@router.delete("/kb/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    collection: str = Query(DEFAULT_COLLECTION, description="Collection name"),
) -> dict:
    client = get_client()
    try:
        client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=[int(doc_id)]),
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"deleted": doc_id, "collection": collection}


@router.get("/health")
async def health(
    collection: str = Query(DEFAULT_COLLECTION, description="Collection name"),
) -> dict:
    try:
        client = get_client()
        info = client.get_collection(collection)
        doc_count = info.points_count or 0
        status = "ok"
    except Exception as exc:
        doc_count = 0
        status = f"error: {exc}"
    return {
        "status": status,
        "doc_count": doc_count,
        "collection": collection,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
