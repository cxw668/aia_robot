"""Knowledge base router.

Endpoints
---------
POST   /kb/ingest          submit ingest job (dir | url | file upload)
GET    /kb/jobs            list ingest jobs
GET    /kb/docs            list / search documents from Qdrant
DELETE /kb/docs/{doc_id}   delete a single document
DELETE /kb/docs            delete all documents
GET    /health             Qdrant status + doc count
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from threading import Thread
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from qdrant_client import models
from app.knowledge_base.rag import _get_client, _get_model

router = APIRouter(tags=["knowledge"])

COLLECTION = "knowledge_base"

# ── In-memory job store ───────────────────────────────────────────────────────
class IngestJob(BaseModel):
    job_id: str
    type: str
    source: str
    status: str
    created_at: str
    doc_count: int = 0
    error: str | None = None

_jobs: OrderedDict[str, dict] = OrderedDict()

def _add_job(job_type: str, source: str) -> str:
    jid = str(uuid.uuid4())[:8]
    _jobs[jid] = {"job_id": jid, "type": job_type, "source": source,
                  "status": "pending", "doc_count": 0,
                  "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "error": None}
    if len(_jobs) > 200:
        _jobs.popitem(last=False)
    return jid

# ── Background workers ────────────────────────────────────────────────────────
def _run_dir(jid: str, path: str) -> None:
    _jobs[jid]["status"] = "running"
    try:
        from app.knowledge_base.ingest import ingest_directory
        results = ingest_directory(path)
        total = sum(r.get("doc_count", 0) for r in results)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = total
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)

def _run_file(jid: str, tmp_path: str, filename: str) -> None:
    import os
    _jobs[jid]["status"] = "running"
    try:
        from app.knowledge_base.ingest import ingest_file
        r = ingest_file(tmp_path)
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

def _run_url(jid: str, url: str) -> None:
    import tempfile, os, requests
    _jobs[jid]["status"] = "running"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        suffix = ".json" if url.endswith(".json") else ".json"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(resp.content)
            tmp = f.name
        from app.knowledge_base.ingest import ingest_file
        r = ingest_file(tmp)
        _jobs[jid]["status"] = "done"
        _jobs[jid]["doc_count"] = r.get("doc_count", 0)
    except Exception as exc:
        _jobs[jid]["status"] = "failed"
        _jobs[jid]["error"] = str(exc)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

# ── Request models ────────────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    type: str
    path: str | None = None
    url: str | None = None

# ── Routes ───────────────────────────────────────────────────────────────────
@router.post("/kb/ingest", status_code=202)
async def ingest(req: IngestRequest) -> dict:
    if req.type == "dir":
        if not req.path:
            raise HTTPException(400, "path required")
        jid = _add_job("dir", req.path)
        Thread(target=_run_dir, args=(jid, req.path), daemon=True).start()
    elif req.type == "url":
        if not req.url:
            raise HTTPException(400, "url required")
        jid = _add_job("url", req.url)
        Thread(target=_run_url, args=(jid, req.url), daemon=True).start()
    else:
        raise HTTPException(400, f"unknown type: {req.type!r}")
    return {"job_id": jid}

@router.post("/kb/upload", status_code=202)
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Upload a JSON file and ingest it."""
    import tempfile, os
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only .json files are supported")
    contents = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        f.write(contents)
        tmp = f.name
    jid = _add_job("file", file.filename)
    Thread(target=_run_file, args=(jid, tmp, file.filename), daemon=True).start()
    return {"job_id": jid}

@router.get("/kb/jobs", response_model=list[IngestJob])
async def list_jobs() -> list[dict]:
    return list(reversed(list(_jobs.values())))

@router.get("/kb/docs")
async def list_docs(
    q: str | None = Query(None, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List or search documents in the knowledge base."""
    client = _get_client()
    try:
        if q and q.strip():
            # Vector search
            model = _get_model()
            vec = model.encode(q, normalize_embeddings=True).tolist()
            hits = client.query_points(
                collection_name=COLLECTION,
                query=vec,
                limit=limit,
                with_payload=True,
            ).points
            docs = [{"id": str(h.id), "score": round(h.score, 4), **h.payload} for h in hits]
            total = len(docs)
        else:
            # Scroll all
            result, _ = client.scroll(
                collection_name=COLLECTION,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            docs = [{"id": str(p.id), "score": None, **p.payload} for p in result]
            info = client.get_collection(COLLECTION)
            total = info.points_count or 0
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"total": total, "offset": offset, "limit": limit, "docs": docs}

@router.delete("/kb/docs/{doc_id}")
async def delete_doc(doc_id: str) -> dict:
    client = _get_client()
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=models.PointIdsList(points=[int(doc_id)]),
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"deleted": doc_id}

@router.delete("/kb/docs")
async def delete_all_docs() -> dict:
    client = _get_client()
    try:
        client.delete_collection(COLLECTION)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"status": "collection deleted"}

@router.get("/health")
async def health() -> dict:
    try:
        client = _get_client()
        info = client.get_collection(COLLECTION)
        doc_count = info.points_count or 0
        status = "ok"
    except Exception as exc:
        doc_count = 0
        status = f"error: {exc}"
    return {"status": status, "doc_count": doc_count,
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
