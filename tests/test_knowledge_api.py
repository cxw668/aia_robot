from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import app.routers.knowledge as knowledge_router
from app.database import JobStatus, KnowledgeIngestJob
from tests.api_test_utils import FakeAsyncSession, create_test_client


class KnowledgeApiTests(unittest.TestCase):
    def test_ingest_endpoint_creates_job_and_wakes_worker(self) -> None:
        db = FakeAsyncSession()
        captured: dict[str, str] = {}

        async def fake_create_ingest_job(
            _db: object,
            *,
            job_id: str,
            job_type: str,
            source: str,
            collection_name: str,
            requested_by: int | None = None,
        ) -> KnowledgeIngestJob:
            captured["job_id"] = job_id
            captured["job_type"] = job_type
            captured["source"] = source
            captured["collection_name"] = collection_name
            return KnowledgeIngestJob(
                id=job_id,
                job_type=job_type,
                source=source,
                collection_name=collection_name,
                status=JobStatus.PENDING,
                requested_by=requested_by,
            )

        with create_test_client(db) as client, \
            patch.object(knowledge_router, "create_ingest_job", new=fake_create_ingest_job), \
            patch.object(knowledge_router, "notify_ingest_worker") as notify_worker:
            response = client.post(
                "/kb/ingest",
                json={
                    "type": "dir",
                    "path": "E:\\aia_robot\\aia_data",
                    "collection": "aia_knowledge_base",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["collection"], "aia_knowledge_base")
        self.assertEqual(captured["job_type"], "dir")
        self.assertEqual(captured["source"], "E:\\aia_robot\\aia_data")
        notify_worker.assert_called_once_with()

    def test_retry_endpoint_requeues_failed_job(self) -> None:
        db = FakeAsyncSession()
        failed_job = KnowledgeIngestJob(
            id="job-retry-1",
            job_type="url",
            source="https://example.com/data.json",
            collection_name="aia_knowledge_base",
            status=JobStatus.FAILED,
        )

        with create_test_client(db) as client, \
            patch.object(knowledge_router, "get_ingest_job", new=AsyncMock(return_value=failed_job)), \
            patch.object(knowledge_router, "requeue_ingest_job", new=AsyncMock(return_value=True)), \
            patch.object(knowledge_router, "notify_ingest_worker") as notify_worker:
            response = client.post("/kb/jobs/job-retry-1/retry")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": "job-retry-1", "status": "pending"})
        notify_worker.assert_called_once_with()

    def test_retry_endpoint_rejects_non_retryable_uploaded_file_job(self) -> None:
        db = FakeAsyncSession()
        failed_job = KnowledgeIngestJob(
            id="job-retry-2",
            job_type="file",
            source="E:\\missing-upload.json",
            collection_name="aia_knowledge_base",
            status=JobStatus.FAILED,
        )

        with create_test_client(db) as client, \
            patch.object(knowledge_router, "get_ingest_job", new=AsyncMock(return_value=failed_job)), \
            patch.object(knowledge_router, "requeue_ingest_job", new=AsyncMock(return_value=True)):
            response = client.post("/kb/jobs/job-retry-2/retry")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "conflict")
        self.assertEqual(
            response.json()["error"]["message"],
            "Uploaded file is no longer available for retry",
        )
