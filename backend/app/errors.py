"""Structured errors, request IDs and cross-cutting HTTP middleware."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings

logger = logging.getLogger("queueless")

REQUEST_ID_HEADER = "X-Request-ID"


class ApiException(Exception):
    """Domain error carrying an HTTP status and machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str, detail: Any = None, headers: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers or {}


def _body(status: int, code: str, message: str, request_id: str, detail: Any = None) -> dict:
    payload: dict[str, Any] = {"error": {"code": code, "message": message, "request_id": request_id}}
    if detail is not None:
        payload["error"]["detail"] = detail
    return payload


def install_middleware(app: FastAPI) -> None:
    settings = get_settings()

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001, ANN202
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        # Conservative security headers suitable for a same-origin government portal.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER, "X-Response-Time-Ms"],
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def _api_exception(request: Request, exc: ApiException):  # noqa: ANN202
        rid = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.status_code, exc.code, exc.message, rid, exc.detail),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):  # noqa: ANN202
        rid = getattr(request.state, "request_id", "-")
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.status_code, code, str(exc.detail), rid),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception(request: Request, exc: RequestValidationError):  # noqa: ANN202
        rid = getattr(request.state, "request_id", "-")
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "invalid")}
            for e in exc.errors()[:10]
        ]
        return JSONResponse(
            status_code=422,
            content=_body(422, "validation_error", "Request validation failed.", rid, errors),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN202
        rid = getattr(request.state, "request_id", "-")
        logger.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
        # Never expose raw tracebacks/Python errors to clients.
        return JSONResponse(
            status_code=500,
            content=_body(500, "internal_error", "An unexpected error occurred. Please try again.", rid),
        )


def install(app: FastAPI) -> None:
    install_middleware(app)
    install_exception_handlers(app)
