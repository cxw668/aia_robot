"""Knowledge base router — multi-collection architecture.

Each collection_name is an independent knowledge base category.

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

import time
import uuid
from collections import OrderedDict
from threading import Thread

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field
from qdrant_client import models

from app.knowledge_base.config import DEFAULT_COLLECTION
from app.knowledge_base.core import get_client, get_model

router = APIRouter(tags=["knowledge"])

# ── In-memory job store ───────────────────────────────────────────────────────
class IngestJob(BaseModel):
    job_id: str
    type: str
    source: str
    collection: str
    status: str
    created_at: str
    doc_count: int = 0
    # 使用 `schema_` 避免与 BaseModel.schema() 方法冲突，外部仍使用 key `schema`
    schema_: str = Field("", alias="schema")
    skipped: int = 0
    failed_items: int = 0
    error: str | None = None
    
    class Config:
        # 允许以字段别名（如来自 _jobs dict 的 'schema'）进行填充
        validate_by_name = True

_jobs: OrderedDict[str, dict] = OrderedDict()

def _add_job(job_type: str, source: str, collection: str) -> str:
    jid = str(uuid.uuid4())[:8]
    _jobs[jid] = {
        "job_id": jid, "type": job_type, "source": source,
        "collection": collection, "status": "pending", "doc_count": 0,
        "schema": "", "skipped": 0, "failed_items": 0,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "error": None,
    }
    if len(_jobs) > 200:
        _jobs.popitem(last=False)
    return jid

# ── Background workers ────────────────────────────────────────────────────────
def _run_dir(jid: str, path: str, collection: str) -> None:
    _jobs[jid]["status"] = "running"
    try:
        from app.knowledge_base.ingestion.pipeline import ingest_directory
        results = ingest_directory(path, collection_name=collection)
        total = sum(r.get("doc_count", 0) for r in results)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = total
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)

def _run_file(jid: str, tmp_path: str, filename: str, collection: str) -> None:
    import os
    _jobs[jid]["status"] = "running"
    try:
        from app.knowledge_base.ingestion.pipeline import ingest_file
        r = ingest_file(tmp_path, collection_name=collection)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = r.get("doc_count", 0)
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

def _run_url(jid: str, url: str, collection: str) -> None:
    import tempfile, os, requests
    _jobs[jid]["status"] = "running"
    tmp = ""
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(resp.content)
            tmp = f.name
        from app.knowledge_base.ingestion.pipeline import ingest_file
        r = ingest_file(tmp, collection_name=collection)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = r.get("doc_count", 0)
        _jobs[jid]["schema"] = r.get("schema", "")
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


def _run_forms_pdf(jid: str, json_path: str) -> None:
    """Background worker: ingest a local forms JSON file via PDF pipeline."""
    _jobs[jid]["status"] = "running"
    try:
        from app.knowledge_base.ingestion.pipeline import ingest_file
        r = ingest_file(json_path)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = r.get("doc_count", 0)
        _jobs[jid]["schema"] = r.get("schema", "forms_pdf")
        _jobs[jid]["skipped"] = r.get("skipped", 0)
        _jobs[jid]["failed_items"] = r.get("failed", 0)
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)


# ── Request models ────────────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    type: str
    path: str | None = None
    url: str | None = None
    collection: str = DEFAULT_COLLECTION

# ── Routes ───────────────────────────────────────────────────────────────────
@router.post("/kb/ingest", status_code=202)
async def ingest(req: IngestRequest) -> dict:
    jid: str = ""
    if req.type == "dir":
        if not req.path:
            raise HTTPException(400, "path required")
        jid = _add_job("dir", req.path, req.collection)
        Thread(target=_run_dir, args=(jid, req.path, req.collection), daemon=True).start()
    elif req.type == "url":
        if not req.url:
            raise HTTPException(400, "url required")
        jid = _add_job("url", req.url, req.collection)
        Thread(target=_run_url, args=(jid, req.url, req.collection), daemon=True).start()
    elif req.type == "forms_pdf":
        # Ingest a local forms JSON file (items with full_url → PDF download pipeline)
        if not req.path:
            raise HTTPException(400, "path required for forms_pdf type")
        jid = _add_job("forms_pdf", req.path, req.collection)
        Thread(target=_run_forms_pdf, args=(jid, req.path), daemon=True).start()
    else:
        raise HTTPException(400, f"unknown type: {req.type!r}  (supported: dir, url, forms_pdf)")
    return {"job_id": jid, "collection": req.collection}

@router.post("/kb/upload", status_code=202)
async def upload_file(
    file: UploadFile = File(...),
    collection: str = Query(DEFAULT_COLLECTION, description="Target collection (category) name"),
) -> dict:
    """Upload a JSON file and ingest it into the specified collection."""
    import tempfile, os
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only .json files are supported")
    contents = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        f.write(contents)
        tmp = f.name
    jid = _add_job("file", file.filename, collection)
    Thread(target=_run_file, args=(jid, tmp, file.filename, collection), daemon=True).start()
    return {"job_id": jid, "collection": collection}

@router.get("/kb/jobs", response_model=list[IngestJob])
async def list_jobs() -> list[dict]:
    return list(reversed(list(_jobs.values())))

# ── Collections (category) management ────────────────────────────────────────
@router.get("/kb/collections")
async def list_collections() -> dict:
    """List all Qdrant collections with their document counts."""
    client = get_client()
    try:
        cols = client.get_collections().collections
        result = []
        for c in cols:
            try:
                info = client.get_collection(c.name)
                result.append({"name": c.name, "doc_count": info.points_count or 0})
            except Exception:
                result.append({"name": c.name, "doc_count": 0})
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

# ── Docs within a collection ──────────────────────────────────────────────────
@router.get("/kb/docs")
async def list_docs(
    collection: str = Query(DEFAULT_COLLECTION, description="Collection (category) name"),
    q: str | None = Query(None, description="Search query"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List or search documents in a specific collection."""
    client = get_client()
    # Check collection exists
    existing = [c.name for c in client.get_collections().collections]
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
            all_docs = [{"id": str(h.id), "score": round(h.score, 4), **h.payload} for h in hits]
        else:
            result, _ = client.scroll(
                collection_name=collection,
                limit=1000,
                offset=0,
                with_payload=True,
                with_vectors=False,
            )
            all_docs = [{"id": str(p.id), "score": None, **p.payload} for p in result]
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
        "status": status, "doc_count": doc_count, "collection": collection,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
