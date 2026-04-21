from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.request_context import get_request_id

logger = logging.getLogger(__name__)

_ERROR_CODE_BY_STATUS: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    408: "request_timeout",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
    504: "upstream_timeout",
}


def _default_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _extract_message(detail: object, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return fallback


def _extract_details(detail: object) -> object | None:
    if isinstance(detail, dict):
        return detail.get("details")
    if isinstance(detail, list):
        return detail
    return None


def build_error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: object | None = None,
) -> dict:
    # Keep one envelope for every error path so clients can branch on
    # error.code without guessing which endpoint produced the response.
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", get_request_id())
    status_code = exc.status_code
    return JSONResponse(
        status_code=status_code,
        content=build_error_payload(
            code=_ERROR_CODE_BY_STATUS.get(
                status_code,
                "request_error" if status_code < 500 else "internal_error",
            ),
            message=_extract_message(exc.detail, _default_message(status_code)),
            request_id=request_id,
            details=_extract_details(exc.detail),
        ),
        headers={"X-Request-ID": request_id},
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", get_request_id())
    return JSONResponse(
        status_code=422,
        content=build_error_payload(
            code="validation_error",
            message="请求参数校验失败。",
            request_id=request_id,
            details=exc.errors(),
        ),
        headers={"X-Request-ID": request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", get_request_id())
    logger.exception(
        "[api] unhandled exception | request_id=%s | path=%s",
        request_id,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=build_error_payload(
            code="internal_error",
            message="系统内部错误，请稍后重试。",
            request_id=request_id,
        ),
        headers={"X-Request-ID": request_id},
    )
