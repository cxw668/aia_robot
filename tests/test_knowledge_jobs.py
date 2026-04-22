from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from app.database import JobStatus, KnowledgeIngestJob
from app.knowledge_jobs import can_retry_ingest_job, serialize_ingest_job, summarize_job_result


class KnowledgeJobTests(unittest.TestCase):
    def test_summarize_single_result_preserves_schema_and_counters(self) -> None:
        summary = summarize_job_result(
            {
                "schema": "forms_markdown",
                "doc_count": 12,
                "skipped": 2,
                "failed": 1,
            }
        )

        self.assertEqual(summary["schema_name"], "forms_markdown")
        self.assertEqual(summary["doc_count"], 12)
        self.assertEqual(summary["skipped_count"], 2)
        self.assertEqual(summary["failed_items"], 1)

    def test_summarize_directory_result_marks_mixed_schema_and_partial_failures(self) -> None:
        summary = summarize_job_result(
            [
                {"schema": "service_categories", "doc_count": 10},
                {"schema": "menu", "doc_count": 3},
                {"schema": "error", "doc_count": 0, "error": "bad file"},
            ]
        )

        self.assertEqual(summary["schema_name"], "mixed")
        self.assertEqual(summary["doc_count"], 13)
        self.assertEqual(summary["failed_items"], 1)
        self.assertEqual(summary["error"], "bad file")

    def test_serialize_ingest_job_matches_api_shape(self) -> None:
        job = KnowledgeIngestJob(
            id="job-001",
            job_type="file",
            source="sample.json",
            collection_name="aia_knowledge_base",
            status=JobStatus.DONE,
            schema_name="menu",
            doc_count=4,
            skipped_count=1,
            failed_items=0,
            error=None,
            created_at=datetime(2026, 4, 21, 12, 0, 0),
            started_at=datetime(2026, 4, 21, 12, 0, 1),
            finished_at=datetime(2026, 4, 21, 12, 0, 2),
        )

        payload = serialize_ingest_job(job)
        self.assertEqual(payload["job_id"], "job-001")
        self.assertEqual(payload["type"], "file")
        self.assertEqual(payload["collection"], "aia_knowledge_base")
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["schema"], "menu")
        self.assertEqual(payload["doc_count"], 4)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["failed_items"], 0)

    def test_can_retry_failed_url_job(self) -> None:
        job = KnowledgeIngestJob(
            id="job-002",
            job_type="url",
            source="https://example.com/data.json",
            collection_name="aia_knowledge_base",
            status=JobStatus.FAILED,
        )

        can_retry, message = can_retry_ingest_job(job)
        self.assertTrue(can_retry)
        self.assertIsNone(message)

    def test_cannot_retry_file_job_when_uploaded_source_is_missing(self) -> None:
        missing_path = os.path.join(tempfile.gettempdir(), "missing-upload.json")
        job = KnowledgeIngestJob(
            id="job-003",
            job_type="file",
            source=missing_path,
            collection_name="aia_knowledge_base",
            status=JobStatus.FAILED,
        )

        can_retry, message = can_retry_ingest_job(job)
        self.assertFalse(can_retry)
        self.assertEqual(message, "Uploaded file is no longer available for retry")
