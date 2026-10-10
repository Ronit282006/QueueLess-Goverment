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
from ..models import (
    Counter,
    CounterService,
    Department,
    Service,
    StaffAssignment,
    StaffAssignmentService,
    User,
)


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


def assigned_service_ids(db: Session, user_id: int, office_id: int | None = None) -> set[int]:
    """Every service the member may serve across their active assignments.

    Mirrors the per-counter rule used for enforcement: an assignment's explicit
    scope wins, otherwise the services its counter is linked to, otherwise (an
    unmapped counter) every service offered by the assignment's office.
    """
    stmt = select(StaffAssignment).where(
        StaffAssignment.user_id == user_id, StaffAssignment.is_active.is_(True)
    )
    if office_id is not None:
        stmt = stmt.where(StaffAssignment.office_id == office_id)

    allowed: set[int] = set()
    for assignment in db.scalars(stmt).all():
        if assignment.counter_id is None:
            continue
        explicit = {s.service_id for s in assignment.services}
        if explicit:
            allowed |= explicit
            continue
        links = set(
            db.scalars(
                select(CounterService.service_id).where(
                    CounterService.counter_id == assignment.counter_id
                )
            ).all()
        )
        if links:
            allowed |= links
            continue
        office_services = set(
            db.scalars(
                select(Service.id)
                .join(Department, Service.department_id == Department.id)
                .where(Department.office_id == assignment.office_id)
            ).all()
        )
        allowed |= office_services
    return allowed


def assigned_service_scope(db: Session, user_id: int, counter_id: int) -> set[int] | None:
    """Services a member may serve at a counter.

    Returns ``None`` when the assignment is unrestricted (no explicit scope
    rows), meaning every service the counter handles is allowed. Otherwise
    returns the explicit set of permitted service ids (possibly empty, which
    should be treated as "no services").
    """
    explicit: set[int] = set()
    has_scope = False
    rows = db.execute(
        select(StaffAssignment.id, StaffAssignmentService.service_id)
        .outerjoin(
            StaffAssignmentService,
            StaffAssignmentService.assignment_id == StaffAssignment.id,
        )
        .where(
            StaffAssignment.user_id == user_id,
            StaffAssignment.counter_id == counter_id,
            StaffAssignment.is_active.is_(True),
        )
    ).all()
    for _assignment_id, service_id in rows:
        if service_id is None:
            continue
        has_scope = True
        explicit.add(service_id)
    return explicit if has_scope else None