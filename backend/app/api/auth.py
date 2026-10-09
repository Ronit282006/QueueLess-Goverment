"""Authentication endpoints: register, login, profile."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiException
from ..models import EmailOTPChallenge, Notification, User
from ..models.enums import NotificationKind, NotificationStatus, Role
from ..schemas.token import TokenOut  # noqa: F401 (kept for grouping clarity)
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services.email_validation import ensure_deliverable_email
from ..services.notify_service import enqueue_email
from ..services.rate_limit import rate_limit

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    tags: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tags: list[str] = []


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class OTPResendRequest(BaseModel):
    email: EmailStr


class RegistrationStarted(BaseModel):
    message: str
    expires_in_seconds: int


class RegistrationVerified(AuthResponse):
    message: str


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role, tags=user.tag_list)


def _otp_hash(email: str, otp: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"{email}:{otp}".encode(), hashlib.sha256).hexdigest()


def _send_registration_otp(db: Session, challenge: EmailOTPChallenge, otp: str) -> None:
    stale = db.scalars(
        select(Notification).where(
            Notification.recipient == challenge.email,
            Notification.kind == NotificationKind.ACCOUNT_OTP.value,
            Notification.status == NotificationStatus.QUEUED.value,
        )
    ).all()
    for notification in stale:
        notification.status = NotificationStatus.FAILED.value
        notification.last_error = "Superseded by a newer verification code."
    enqueue_email(
        db,
        recipient=challenge.email,
        subject="Your QueueLess verification code",
        body=f"Hello {challenge.full_name}, your QueueLess verification code is {otp}. It expires in 5 minutes. If you did not request this, ignore this email.",
        kind=NotificationKind.ACCOUNT_OTP,
        dedupe_key=f"account-otp:{challenge.id}:{challenge.send_count}:{secrets.token_hex(6)}",
        sensitive=True,
    )


@router.post("/register", response_model=RegistrationStarted, status_code=202, dependencies=[Depends(rate_limit("register", 5))])
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegistrationStarted:
    email = ensure_deliverable_email(body.email)
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiException(409, "email_taken", "An account with this email already exists.")
    now = datetime.now(timezone.utc)
    challenge = db.scalar(select(EmailOTPChallenge).where(EmailOTPChallenge.email == email))
    if challenge is not None:
        raise ApiException(409, "registration_pending", "A verification code is already pending. Verify it or request a resend.")
    challenge = EmailOTPChallenge(
            email=email, full_name=body.full_name,
            password_hash=hash_password(body.password),
            tags=",".join(sorted({t.strip().lower() for t in body.tags if t.strip()})),
            otp_hash="", expires_at=now, send_window_started_at=now, last_sent_at=now, send_count=0,
    )
    db.add(challenge)
    db.flush()
    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge.otp_hash = _otp_hash(email, otp)
    challenge.expires_at = now + timedelta(minutes=get_settings().otp_expiry_min)
    challenge.attempts = 0
    challenge.send_count += 1
    challenge.last_sent_at = now
    _send_registration_otp(db, challenge, otp)
    return RegistrationStarted(message="Verification code sent.", expires_in_seconds=get_settings().otp_expiry_min * 60)


@router.post("/register/resend", response_model=RegistrationStarted, dependencies=[Depends(rate_limit("register_resend", 5))])
def resend_registration_otp(body: OTPResendRequest, db: Session = Depends(get_db)) -> RegistrationStarted:
    email = ensure_deliverable_email(body.email)
    challenge = db.scalar(select(EmailOTPChallenge).where(EmailOTPChallenge.email == email))
    if challenge is None or db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ApiException(404, "registration_not_found", "No pending registration exists for that email.")
    now = datetime.now(timezone.utc)
    last_sent = challenge.last_sent_at.replace(tzinfo=timezone.utc) if challenge.last_sent_at.tzinfo is None else challenge.last_sent_at
    elapsed = (now - last_sent).total_seconds()
    settings = get_settings()
    if elapsed < settings.otp_resend_cooldown_sec:
        retry = max(1, int(settings.otp_resend_cooldown_sec - elapsed))
        raise ApiException(429, "otp_resend_limited", "Please wait before requesting another code.", {"retry_after": retry}, headers={"Retry-After": str(retry)})
    window = challenge.send_window_started_at.replace(tzinfo=timezone.utc) if challenge.send_window_started_at.tzinfo is None else challenge.send_window_started_at
    if now - window >= timedelta(hours=1):
        challenge.send_count = 0
        challenge.send_window_started_at = now
    if challenge.send_count >= settings.otp_max_sends_per_hour:
        raise ApiException(429, "otp_resend_limited", "Too many codes requested. Try again later.")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    challenge.otp_hash = _otp_hash(email, otp)
    challenge.expires_at = now + timedelta(minutes=settings.otp_expiry_min)
    challenge.attempts = 0
    challenge.send_count += 1
    challenge.last_sent_at = now
    _send_registration_otp(db, challenge, otp)
    return RegistrationStarted(message="A new verification code was sent.", expires_in_seconds=settings.otp_expiry_min * 60)


@router.post("/register/verify", response_model=RegistrationVerified, dependencies=[Depends(rate_limit("register_verify", 10))])
def verify_registration_otp(body: OTPVerifyRequest, db: Session = Depends(get_db)) -> RegistrationVerified:
    email = body.email.lower()
    challenge = db.scalar(select(EmailOTPChallenge).where(EmailOTPChallenge.email == email))
    if challenge is None:
        raise ApiException(400, "invalid_otp", "The verification code is invalid or expired.")
    now = datetime.now(timezone.utc)
    expiry = challenge.expires_at.replace(tzinfo=timezone.utc) if challenge.expires_at.tzinfo is None else challenge.expires_at
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
    user = User(
        email=email, full_name=challenge.full_name, password_hash=challenge.password_hash,
        role=Role.CITIZEN.value, tags=challenge.tags, is_active=True,
    )
    db.add(user)
    db.flush()
    db.delete(challenge)
    enqueue_email(
        db, recipient=user.email, user_id=user.id, subject="Welcome to QueueLess",
        body=f"Welcome to QueueLess, {user.full_name}! Your account has been created successfully.",
        kind=NotificationKind.ACCOUNT_WELCOME, dedupe_key=f"welcome:{user.id}",
    )
    access = create_access_token(subject=user.id, role=user.role)
    db.commit()
    return RegistrationVerified(
        access_token=access, user=_user_out(user),
        message=f"Welcome to QueueLess, {user.full_name}! Your account has been created successfully.",
    )


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(rate_limit("login", 10))])
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Generic message prevents account enumeration.
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiException(401, "invalid_credentials", "Incorrect email or password.")
    if not user.is_active:
        raise ApiException(403, "account_disabled", "This account has been disabled.")
    token = create_access_token(subject=user.id, role=user.role)
    return AuthResponse(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)
