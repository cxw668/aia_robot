from __future__ import annotations

import asyncio
import json
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from app.errors import build_error_payload, http_exception_handler


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)
    request.state.request_id = "req-test-001"
    return request


class ErrorPayloadTests(unittest.TestCase):
    def test_build_error_payload_uses_uniform_shape(self) -> None:
        payload = build_error_payload(
            code="bad_request",
            message="参数错误",
            request_id="req-1",
            details={"field": "query"},
        )

        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertEqual(payload["error"]["message"], "参数错误")
        self.assertEqual(payload["error"]["request_id"], "req-1")
        self.assertEqual(payload["error"]["details"], {"field": "query"})

    def test_http_exception_handler_attaches_request_id_header(self) -> None:
        response = asyncio.run(
            http_exception_handler(
                _make_request(),
                HTTPException(status_code=404, detail="Session not found"),
            )
        )

        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["X-Request-ID"], "req-test-001")
        self.assertEqual(body["error"]["code"], "not_found")
        self.assertEqual(body["error"]["message"], "Session not found")
        self.assertEqual(body["error"]["request_id"], "req-test-001")
