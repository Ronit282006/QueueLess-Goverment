"""Shared enumerations for the QueueLess domain."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    CITIZEN = "CITIZEN"
    STAFF = "STAFF"
    ADMIN = "ADMIN"


class TokenStatus(str, enum.Enum):
    CREATED = "CREATED"
    WAITING = "WAITING"
    APPROACHING = "APPROACHING"
    ARRIVED = "ARRIVED"
    CALLED = "CALLED"
    SERVING = "SERVING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    RESCHEDULED = "RESCHEDULED"


class TokenStage(str, enum.Enum):
    """Smart come-to-office stages shown to the citizen."""

    SAFE = "SAFE"          # green: safely in the queue, stay where you are
    APPROACHING = "APPROACHING"  # yellow: turn is approaching
    COME_NOW = "COME_NOW"  # red: proceed to the office
    YOUR_TURN = "YOUR_TURN"  # red: at the counter


class CounterStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    BREAK = "BREAK"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"


class NotificationKind(str, enum.Enum):
    TOKEN_CREATED = "TOKEN_CREATED"
    QUEUE_APPROACHING = "QUEUE_APPROACHING"
    COME_TO_OFFICE = "COME_TO_OFFICE"
    TOKEN_CALLED = "TOKEN_CALLED"
    COUNTER_ASSIGNED = "COUNTER_ASSIGNED"
    TOKEN_SKIPPED = "TOKEN_SKIPPED"
    SERVICE_COMPLETED = "SERVICE_COMPLETED"
    QUEUE_DELAY = "QUEUE_DELAY"
    INCIDENT_ACTION_REQUIRED = "INCIDENT_ACTION_REQUIRED"
    TOKEN_TRANSFERRED = "TOKEN_TRANSFERRED"
    TOKEN_CANCELLED = "TOKEN_CANCELLED"
    ACCOUNT_OTP = "ACCOUNT_OTP"
    ACCOUNT_WELCOME = "ACCOUNT_WELCOME"
    SERVICE_LOCATION_CHANGED = "SERVICE_LOCATION_CHANGED"
    TOKEN_TRANSFER_REQUESTED = "TOKEN_TRANSFER_REQUESTED"


class NotificationStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    LOGGED = "LOGGED"
    FAILED = "FAILED"


class RecommendationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DataOrigin(str, enum.Enum):
    """Provenance flag so demo data is never mistaken for real records."""

    LIVE = "LIVE"
    DEMO = "DEMO"
