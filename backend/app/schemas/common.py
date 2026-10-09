"""Shared Pydantic schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    detail: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    worker: str = "unknown"
    email_mode: str
    version: str = "1.0.0"
    time: datetime