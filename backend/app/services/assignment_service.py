"""Counter/office authorization for staff-facing operations.

The `staff_assignments` table is the single source of truth for which counters
a staff member may operate. Every staff request that touches a counter or an
office-scoped dashboard re-validates the assignment inside the request's own
transaction, so changing a counter id in the URL, query string or body can
never widen a member's access.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiException
from ..models import Counter, StaffAssignment, User


def assigned_office_ids(db: Session, user_id: int) -> list[int]:
    """Ordered list of office ids the member has an active assignment in."""
    return list(
        db.scalars(
            select(StaffAssignment.office_id)
            .where(StaffAssignment.user_id == user_id, StaffAssignment.is_active.is_(True))
            .distinct()
            .order_by(StaffAssignment.office_id)
        ).all()
    )


def assigned_counter_ids(db: Session, user_id: int, office_id: int | None = None) -> set[int]:
    stmt = select(StaffAssignment.counter_id).where(
        StaffAssignment.user_id == user_id, StaffAssignment.is_active.is_(True)
    )
    if office_id is not None:
        stmt = stmt.where(StaffAssignment.office_id == office_id)
    return {cid for cid in db.scalars(stmt).all() if cid is not None}


def assigned_counts_by_office(db: Session, user_id: int) -> dict[int, int]:
    rows = db.execute(
        select(StaffAssignment.office_id, StaffAssignment.counter_id)
        .where(StaffAssignment.user_id == user_id, StaffAssignment.is_active.is_(True))
    ).all()
    counts: dict[int, int] = {}
    for office_id, counter_id in rows:
        if counter_id is not None:
            counts[office_id] = counts.get(office_id, 0) + 1
    return counts


def is_counter_assigned(db: Session, user: User, counter: Counter) -> bool:
    return any(
        cid == counter.id
        for cid in assigned_counter_ids(db, user.id, counter.office_id)
    )


def require_counter_assignment(db: Session, user: User, counter: Counter) -> None:
    """403 unless the caller may operate this specific counter."""
    if not is_counter_assigned(db, user, counter):
        raise ApiException(
            403, "counter_not_assigned",
            "This counter is not assigned to your account. Please contact your administrator.",
        )


def require_office_scope(db: Session, user: User, office_id: int) -> None:
    """403 for STAFF members without an active assignment in `office_id`.

    Admins retain their administrative scope over every office.
    """
    if user.role == "ADMIN":
        return
    if office_id not in set(assigned_office_ids(db, user.id)):
        raise ApiException(
            403, "office_not_assigned",
            "You do not have any assigned counters in this office.",
        )


def counter_serves(counter: Counter, service_id: int, handled: set[int] | None = None) -> bool:
    """Existing eligibility rule: an unmapped counter serves every service."""
    if not handled:
        return True
    if counter.id in handled:
        return True
    return False