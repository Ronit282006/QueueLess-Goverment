"""Admin staff management: email OTP verification and staff/counter assignment.

Staff accounts are never created before the intended email address is proven by
an OTP. The verified challenge is bound to its email and to the
staff-creation operation only: it cannot be spent on the citizen registration
flow, transferred to another email, or reused after the account exists.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiException
from ..models import (
    Counter,
    Office,
    StaffAssignment,
    StaffOTPChallenge,
    User,
)
from ..models.enums import NotificationKind, Role
from ..security import hash_password, require_admin
from ..services import audit_service, notify_service
from ..services.email_validation import ensure_deliverable_email
from ..services.rate_limit import rate_limit

router = APIRouter(prefix="/api/admin/staff", tags=["Admin"], dependencies=[Depends(require_admin)])
counters_router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

# How long a successfully-verified email may be spent on account creation.
VERIFY_GRACE_MIN = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _otp_hash(email: str, otp: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"{email}:{otp}".encode(), hashlib.sha256).hexdigest()


def _send_otp_email(db: Session, challenge: StaffOTPChallenge, otp: str) -> None:
    from ..models import Notification
    from ..models.enums import NotificationStatus

    # Supercede any earlier queued code for the same address so the mailbox
    # never holds two live OTPs.
    stale = db.scalars(
        select(Notification).where(
            Notification.recipient == challenge.email,
            Notification.kind == NotificationKind.ACCOUNT_OTP.value,
            Notification.status == NotificationStatus.QUEUED.value,
        )
    ).all()
    for notification in stale:
        notification.status = NotificationStatus.FAILED.value
        notification.last_error = "Superseded by a newer staff creation code."
    notify_service.enqueue_email(
        db,
        recipient=challenge.email,
        subject="Your QueueLess staff account verification code",
        body=(
            f"Hello {challenge.full_name}, an administrator requested that a staff "
            f"account be created for {challenge.email}. Your verification code is {otp}. "
            f"It expires in {get_settings().otp_expiry_min} minutes. If you did not expect "
            "this email, you can ignore it — the account will not be created until the "
            "code is verified."
        ),
        kind=NotificationKind.ACCOUNT_OTP,
        dedupe_key=f"staff-otp:{challenge.id}:{challenge.send_count}:{secrets.token_hex(6)}",
        sensitive=True,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class StaffOTPSendRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class StaffOTPSendOut(BaseModel):
    message: str
    expires_in_seconds: int


class StaffOTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class StaffOTPVerifyOut(BaseModel):
    message: str
    verified: bool = True


class StaffCreateRequest(BaseModel):
    email: EmailStr


class StaffCreatedOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str = Role.STAFF.value
    is_active: bool = True
    message: str


class CounterAssignmentIn(BaseModel):
    office_id: int
    counter_ids: list[int] = Field(default_factory=list)
    title: str = Field(default="Service Officer", max_length=80)
    shift_start: str = Field(default="09:30", max_length=10)
    shift_end: str = Field(default="18:00", max_length=10)


# ---------------------------------------------------------------------------
# OTP send / resend / verify
# ---------------------------------------------------------------------------
@router.post("/otp", response_model=StaffOTPSendOut, status_code=202, dependencies=[Depends(rate_limit("staff_otp_send", 5))])
def send_staff_otp(body: StaffOTPSendRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> StaffOTPSendOut:
    if body.password != body.confirm_password:
        raise ApiException(422, "password_mismatch", "Passwords do not match.")
    email = ensure_deliverable_email(body.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ApiException(409, "email_taken", "An account with this email already exists.")

    now = _utcnow()
    settings = get_settings()
    challenge = db.scalar(select(StaffOTPChallenge).where(StaffOTPChallenge.email == email))
    if challenge is not None:
        last_sent = _aware(challenge.last_sent_at)
        elapsed = (now - last_sent).total_seconds()
        if elapsed < settings.otp_resend_cooldown_sec:
            retry = max(1, int(settings.otp_resend_cooldown_sec - elapsed))
            raise ApiException(
                429, "otp_resend_limited", "Please wait before requesting another code.",
                {"retry_after": retry}, headers={"Retry-After": str(retry)},
            )
        window = _aware(challenge.send_window_started_at)
        if now - window >= timedelta(hours=1):
            challenge.send_count = 0
            challenge.send_window_started_at = now
        if challenge.send_count >= settings.otp_max_sends_per_hour:
            raise ApiException(429, "otp_resend_limited", "Too many codes requested. Try again later.")
        challenge.full_name = body.full_name
        challenge.password_hash = hash_password(body.password)
        challenge.verified_at = None  # a fresh code invalidates any earlier verification
        challenge.attempts = 0
        challenge.expires_at = now + timedelta(minutes=settings.otp_expiry_min)
        challenge.last_sent_at = now
        challenge.send_count += 1
        challenge.created_by = admin.id
    else:
        # A pending challenge for another operation/email is never reused; the
        # dedicated table guarantees the OTP stays bound to this email.
        challenge = StaffOTPChallenge(
            email=email,
            full_name=body.full_name,
            password_hash=hash_password(body.password),
            otp_hash="",
            expires_at=now + timedelta(minutes=settings.otp_expiry_min),
            send_window_started_at=now,
            last_sent_at=now,
            send_count=0,
            created_by=admin.id,
        )
        db.add(challenge)
        db.flush()
        challenge.send_count += 1

    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge.otp_hash = _otp_hash(email, otp)
    challenge.attempts = 0
    challenge.last_sent_at = now
    _send_otp_email(db, challenge, otp)
    db.commit()
    return StaffOTPSendOut(
        message=f"A six-digit verification code was sent to {email}.",
        expires_in_seconds=settings.otp_expiry_min * 60,
    )


@router.post("/otp/verify", response_model=StaffOTPVerifyOut, dependencies=[Depends(rate_limit("staff_otp_verify", 10))])
def verify_staff_otp(body: StaffOTPVerifyRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> StaffOTPVerifyOut:
    email = body.email.lower().strip()
    challenge = db.scalar(select(StaffOTPChallenge).where(StaffOTPChallenge.email == email))
    if challenge is None:
        raise ApiException(400, "invalid_otp", "The verification code is invalid or expired.")
    now = _utcnow()
    expiry = _aware(challenge.expires_at)
    if expiry <= now or challenge.attempts >= get_settings().otp_max_verify_attempts:
        db.delete(challenge)
        db.commit()
        raise ApiException(400, "invalid_otp", "The verification code is invalid or expired. Request a new code.")
    if not hmac.compare_digest(challenge.otp_hash, _otp_hash(email, body.otp)):
        challenge.attempts += 1
        if challenge.attempts >= get_settings().otp_max_verify_attempts:
            db.delete(challenge)
        db.commit()
        raise ApiException(400, "invalid_otp", "The verification code is invalid or expired.")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        db.delete(challenge)
        db.commit()
        raise ApiException(409, "email_taken", "An account with this email already exists.")
    if challenge.verified_at is None:
        challenge.verified_at = now
        audit_service.record(
            db, action="staff.email_verified", actor_id=admin.id, actor_role=admin.role,
            entity_type="staff_otp_challenge", entity_id=challenge.id, detail={"email": email},
        )
    db.commit()
    return StaffOTPVerifyOut(
        message="Email verified. You can now create the staff account.",
    )


# ---------------------------------------------------------------------------
# Staff account creation / listing
# ---------------------------------------------------------------------------
@router.post("", response_model=StaffCreatedOut, status_code=201, dependencies=[Depends(rate_limit("staff_create", 10))])
def create_staff(body: StaffCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> StaffCreatedOut:
    email = body.email.lower().strip()
    challenge = db.scalar(
        select(StaffOTPChallenge).where(StaffOTPChallenge.email == email).with_for_update()
    )
    if challenge is None or challenge.verified_at is None:
        raise ApiException(409, "verification_required", "Verify the email address with the OTP before creating the staff account.")
    now = _utcnow()
    verified_at = _aware(challenge.verified_at)
    if now > verified_at + timedelta(minutes=VERIFY_GRACE_MIN):
        db.delete(challenge)
        db.commit()
        raise ApiException(409, "verification_expired", "The email verification has expired. Request a new code and verify again.")

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        db.delete(challenge)
        db.commit()
        raise ApiException(409, "email_taken", "An account with this email already exists.")

    staff_user = User(
        email=email,
        full_name=challenge.full_name,
        password_hash=challenge.password_hash,
        role=Role.STAFF.value,
        is_active=True,
    )
    try:
        with db.begin_nested():
            db.add(staff_user)
            db.flush()
    except IntegrityError:
        # A concurrent request created the same email first.
        raise ApiException(409, "email_taken", "An account with this email already exists.") from None

    audit_service.record(
        db, action="staff.created", actor_id=admin.id, actor_role=admin.role,
        entity_type="user", entity_id=staff_user.id,
        detail={"email": email, "full_name": challenge.full_name, "role": Role.STAFF.value},
    )
    notify_service.enqueue_email(
        db,
        recipient=staff_user.email,
        user_id=staff_user.id,
        subject="Welcome to QueueLess staff portal",
        body=(
            f"Hello {staff_user.full_name}, your staff account for QueueLess is ready. "
            "You can sign in with the email address and password set by your administrator. "
            "Counters will appear on your dashboard once your administrator assigns them."
        ),
        kind=NotificationKind.ACCOUNT_WELCOME,
        dedupe_key=f"staff-welcome:{staff_user.id}",
    )
    db.delete(challenge)
    db.commit()
    return StaffCreatedOut(
        id=staff_user.id, email=staff_user.email, full_name=staff_user.full_name,
        is_active=staff_user.is_active,
        message=f"Staff account created for {staff_user.full_name} ({staff_user.email}).",
    )


@router.get("")
def list_staff(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    users = db.scalars(
        select(User).where(User.role == Role.STAFF.value).order_by(User.created_at, User.id)
    ).all()
    return [_staff_member_row(db, u) for u in users]


@router.get("/{user_id}")
def staff_detail(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None or user.role != Role.STAFF.value:
        raise ApiException(404, "not_found", "Staff member not found.")
    return _staff_member_row(db, user)


# ---------------------------------------------------------------------------
# Counter assignments
# ---------------------------------------------------------------------------
@router.get("/{user_id}/assignments")
def get_staff_assignments(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    user = db.get(User, user_id)
    if user is None or user.role != Role.STAFF.value:
        raise ApiException(404, "not_found", "Staff member not found.")
    rows = db.scalars(
        select(StaffAssignment)
        .where(StaffAssignment.user_id == user_id)
        .order_by(StaffAssignment.office_id, StaffAssignment.counter_id)
    ).all()
    return [_assignment_row(a) for a in rows]


@router.put("/{user_id}/assignments")
def set_staff_assignments(
    user_id: int,
    body: CounterAssignmentIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None or user.role != Role.STAFF.value:
        raise ApiException(404, "not_found", "Staff member not found.")
    office = db.get(Office, body.office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    requested = set(dict.fromkeys(body.counter_ids))
    if requested:
        counters = db.scalars(select(Counter).where(Counter.id.in_(requested))).all()
        by_id = {c.id: c for c in counters}
        if len(by_id) != len(requested):
            raise ApiException(400, "invalid_counter", "One or more counters do not exist.")
        for counter_id in requested:
            if by_id[counter_id].office_id != office.id:
                raise ApiException(400, "cross_office_assignment", "Every counter must belong to the selected office.")

    existing = list(
        db.scalars(
            select(StaffAssignment)
            .where(StaffAssignment.user_id == user_id, StaffAssignment.office_id == office.id)
            .order_by(StaffAssignment.counter_id)
        ).all()
    )
    before = [a.counter_id for a in existing if a.counter_id is not None]
    existing_by_counter = {a.counter_id: a for a in existing if a.counter_id is not None}

    # One active assignment row per (user, counter): drop removed counters,
    # refresh kept ones, and insert newly assigned ones.
    for assignment in existing:
        if assignment.counter_id is not None and assignment.counter_id not in requested:
            db.delete(assignment)
    for counter_id in requested:
        assignment = existing_by_counter.get(counter_id)
        if assignment is not None:
            assignment.title = body.title
            assignment.shift_start = body.shift_start
            assignment.shift_end = body.shift_end
            assignment.is_active = True
        else:
            db.add(
                StaffAssignment(
                    user_id=user.id,
                    office_id=office.id,
                    counter_id=counter_id,
                    title=body.title,
                    shift_start=body.shift_start,
                    shift_end=body.shift_end,
                    is_active=True,
                )
            )
    audit_service.record(
        db, action="staff.assignments_updated", actor_id=admin.id, actor_role=admin.role,
        entity_type="user", entity_id=user.id, office_id=office.id,
        detail={
            "office_id": office.id,
            "before": sorted(before),
            "after": sorted(requested),
            "title": body.title,
            "shift_start": body.shift_start,
            "shift_end": body.shift_end,
        },
    )
    db.commit()
    rows = db.scalars(
        select(StaffAssignment)
        .where(StaffAssignment.user_id == user_id, StaffAssignment.office_id == office.id)
        .order_by(StaffAssignment.counter_id)
    ).all()
    return {"office_id": office.id, "assignments": [_assignment_row(a) for a in rows], "staff_id": user.id}


@counters_router.get("/counters")
def admin_counters(office_id: int = Query(...), admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    """Every counter in an office with the staff currently assigned to it."""
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    counters = db.scalars(
        select(Counter).where(Counter.office_id == office_id).order_by(Counter.number)
    ).all()
    staff_rows = db.execute(
        select(StaffAssignment.user_id, StaffAssignment.counter_id, User.email, User.full_name)
        .join(User, User.id == StaffAssignment.user_id)
        .where(StaffAssignment.office_id == office_id, StaffAssignment.is_active.is_(True))
    ).all()
    by_counter: dict[int, list[dict]] = {}
    for user_id, counter_id, email, full_name in staff_rows:
        if counter_id is None:
            continue
        by_counter.setdefault(counter_id, []).append(
            {"user_id": user_id, "email": email, "full_name": full_name}
        )
    return [
        {
            "id": c.id,
            "number": c.number,
            "name": c.name,
            "status": c.status,
            "office_id": c.office_id,
            "staff": by_counter.get(c.id, []),
        }
        for c in counters
    ]


# ---------------------------------------------------------------------------
# Row serialisers
# ---------------------------------------------------------------------------
def _assignment_row(a: StaffAssignment) -> dict:
    return {
        "office_id": a.office_id,
        "counter_id": a.counter_id,
        "title": a.title,
        "shift_start": a.shift_start,
        "shift_end": a.shift_end,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _staff_member_row(db: Session, user: User) -> dict:
    rows = db.execute(
        select(StaffAssignment.office_id, StaffAssignment.counter_id, StaffAssignment.is_active)
        .where(StaffAssignment.user_id == user.id)
    ).all()
    offices = sorted({office_id for office_id, _counter_id, is_active in rows if is_active})
    counters = sorted({counter_id for _office_id, counter_id, is_active in rows if is_active and counter_id is not None})
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "offices": offices,
        "counters": counters,
        "assignments": [_assignment_row(a) for a in db.scalars(
            select(StaffAssignment).where(StaffAssignment.user_id == user.id).order_by(StaffAssignment.office_id, StaffAssignment.counter_id)
        ).all()],
    }