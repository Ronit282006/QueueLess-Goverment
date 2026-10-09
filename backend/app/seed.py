"""Seed the database with clearly-labelled DEMO data.

    python -m app.seed            # seed if empty
    python -m app.seed --force    # wipe and reseed

Every historical row is written with origin="DEMO". These are simulated
figures for demonstration and model bootstrapping — never real government data.
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .db import Base, SessionLocal, engine
from .models import (
    Counter,
    CounterService,
    Department,
    Feedback,
    Office,
    PriorityRule,
    QueueSnapshot,
    Service,
    ServiceTimeRecord,
    StaffAssignment,
    Token,
    TokenEvent,
    TokenSequence,
    User,
)
from .models.enums import CounterStatus, DataOrigin, Role, TokenStatus
from .security import hash_password

random.seed(20261007)

DEMO_PASSWORD = "Demo@1234"

OFFICES = [
    {
        "code": "gov-main",
        "name": "Central Government Service Center",
        "address": "Sector 11, Gandhinagar, Gujarat",
        "working_hours": "09:30-18:00",
        "counter_count": 10,
        "departments": [
            {
                "name": "Revenue Department",
                "description": "Land records, income and property certification.",
                "services": [
                    {
                        "code": "income-cert",
                        "name": "Income Certificate",
                        "description": "Official certificate of annual household income used for scholarships and welfare schemes.",
                        "documents": ["Aadhaar card", "Address proof", "Income proof / salary slip", "Passport-size photo"],
                        "average_service_min": 6.2,
                        "counters": [1, 2, 3, 4, 10],
                    },
                    {
                        "code": "property-tax",
                        "name": "Property Tax Certificate",
                        "description": "Certificate for property tax assessment and dues clearance.",
                        "documents": ["Aadhaar card", "Property ownership document", "Last tax receipt"],
                        "average_service_min": 7.5,
                        "counters": [5],
                    },
                    {
                        "code": "land-record",
                        "name": "Land Record (7/12 Extract)",
                        "description": "Official extract of land ownership records.",
                        "documents": ["Aadhaar card", "Survey number", "Previous land record"],
                        "average_service_min": 8.0,
                        "counters": [9],
                    },
                ],
            },
            {
                "name": "Municipal Services",
                "description": "Water, drainage and trade licensing.",
                "services": [
                    {
                        "code": "water-connection",
                        "name": "Water Connection",
                        "description": "New or transferred municipal water connection.",
                        "documents": ["Aadhaar card", "Property document", "No-dues certificate"],
                        "average_service_min": 9.0,
                        "counters": [8],
                    },
                    {
                        "code": "trade-license",
                        "name": "Trade License",
                        "description": "Licence to operate a commercial establishment.",
                        "documents": ["Aadhaar card", "Shop ownership / rent agreement", "GST registration"],
                        "average_service_min": 10.5,
                        "counters": [8],
                    },
                ],
            },
            {
                "name": "Civil Registry",
                "description": "Birth, death and residence registration.",
                "services": [
                    {
                        "code": "birth-cert",
                        "name": "Birth Certificate",
                        "description": "Registration and issuance of a birth certificate.",
                        "documents": ["Hospital record", "Parents' Aadhaar", "Address proof"],
                        "average_service_min": 5.0,
                        "counters": [6],
                    },
                    {
                        "code": "residence-cert",
                        "name": "Residence Certificate",
                        "description": "Proof of residence for a given address.",
                        "documents": ["Aadhaar card", "Address proof", "Ration card"],
                        "average_service_min": 5.5,
                        "counters": [7, 10],
                    },
                ],
            },
        ],
    },
    {
        "code": "gov-district",
        "name": "District Service Center — Ahmedabad",
        "address": "Navrangpura, Ahmedabad, Gujarat",
        "working_hours": "10:00-17:30",
        "counter_count": 4,
        "departments": [
            {
                "name": "Revenue Department",
                "description": "Certificates and welfare documents.",
                "services": [
                    {
                        "code": "caste-cert",
                        "name": "Caste Certificate",
                        "description": "Caste certificate for education and employment reservations.",
                        "documents": ["Aadhaar card", "Parents' caste proof", "Address proof"],
                        "average_service_min": 7.0,
                        "counters": [1, 2],
                    },
                    {
                        "code": "income-cert-2",
                        "name": "Income Certificate",
                        "description": "Income certificate (district office).",
                        "documents": ["Aadhaar card", "Address proof", "Income proof"],
                        "average_service_min": 6.0,
                        "counters": [1, 2],
                    },
                ],
            },
            {
                "name": "Social Welfare",
                "description": "Support schemes for citizens.",
                "services": [
                    {
                        "code": "senior-card",
                        "name": "Senior Citizen Card",
                        "description": "Card for senior citizen benefits and concessions.",
                        "documents": ["Aadhaar card", "Age proof", "Address proof"],
                        "average_service_min": 6.5,
                        "counters": [3],
                    },
                    {
                        "code": "disability-cert",
                        "name": "Disability Certificate",
                        "description": "Medical-based disability certification.",
                        "documents": ["Aadhaar card", "Medical report", "Passport-size photo"],
                        "average_service_min": 12.0,
                        "counters": [4],
                    },
                ],
            },
        ],
    },
]

CITIZENS = [
    ("Riya Shah", "citizen@queueless.demo", []),
    ("Arjun Mehta", "arjun.mehta@example.com", []),
    ("Meera Patel", "meera.patel@example.com", ["senior"]),
    ("Ishaan Desai", "ishaan.desai@example.com", []),
    ("Nisha Trivedi", "nisha.trivedi@example.com", ["pregnant"]),
    ("Karan Joshi", "karan.joshi@example.com", []),
    ("Pooja Nair", "pooja.nair@example.com", []),
    ("Vikram Singh", "vikram.singh@example.com", ["disability"]),
    ("Ananya Rao", "ananya.rao@example.com", []),
    ("Devansh Kumar", "devansh.kumar@example.com", []),
]

# Hourly demand weights (09:00–17:00) → peak around 10:00–13:00.
HOUR_WEIGHTS = [0.55, 1.0, 1.25, 1.35, 1.1, 0.7, 0.6, 0.75, 1.15]
DAY_WEIGHTS = {0: 1.25, 1: 1.1, 2: 1.0, 3: 1.0, 4: 1.15, 5: 1.3, 6: 0.0}


def _clear(db) -> None:
    for model in (
        Feedback,
        ServiceTimeRecord,
        QueueSnapshot,
        TokenEvent,
        Token,
        TokenSequence,
        CounterService,
        StaffAssignment,
        Counter,
        PriorityRule,
        Service,
        Department,
        Office,
        User,
    ):
        db.execute(delete(model))
    db.flush()


def seed(force: bool = False) -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.scalar(select(Office.id).limit(1))
        if existing and not force:
            print("Database already contains offices — skipping. Use --force to reseed.")
            return
        if existing and force:
            print("Clearing existing data…")
            _clear(db)

        # ---- Users ------------------------------------------------------
        admin = User(
            email="admin@queueless.demo",
            full_name="Anita Verma",
            password_hash=hash_password(DEMO_PASSWORD),
            role=Role.ADMIN.value,
        )
        staff_users = [
            User(
                email="staff@queueless.demo",
                full_name="Rakesh Sharma",
                password_hash=hash_password(DEMO_PASSWORD),
                role=Role.STAFF.value,
            ),
            User(
                email="staff2@queueless.demo",
                full_name="Priya Menon",
                password_hash=hash_password(DEMO_PASSWORD),
                role=Role.STAFF.value,
            ),
        ]
        citizens = [
            User(
                email=email,
                full_name=name,
                password_hash=hash_password(DEMO_PASSWORD),
                role=Role.CITIZEN.value,
                tags=",".join(tags),
            )
            for name, email, tags in CITIZENS
        ]
        db.add_all([admin, *staff_users, *citizens])
        db.flush()

        staff_pool = [*staff_users, admin]
        services_by_code: dict[str, Service] = {}

        # ---- Offices / departments / services / counters ----------------
        for index, spec in enumerate(OFFICES):
            office = Office(
                code=spec["code"],
                name=spec["name"],
                address=spec["address"],
                working_hours=spec["working_hours"],
                sla_target_wait_min=20 if index == 0 else 25,
                no_show_grace_min=3,
                eta_alert_threshold_min=15,
            )
            db.add(office)
            db.flush()

            counters = [
                Counter(office_id=office.id, number=n, name=f"Counter {n}", status=CounterStatus.AVAILABLE.value)
                for n in range(1, spec["counter_count"] + 1)
            ]
            db.add_all(counters)
            db.flush()
            counter_by_number = {c.number: c for c in counters}

            # Assign staff to the first counters.
            for i, counter in enumerate(counters[: len(staff_pool)]):
                counter.staff_id = staff_pool[i].id
                db.add(
                    StaffAssignment(
                        user_id=staff_pool[i].id,
                        office_id=office.id,
                        counter_id=counter.id,
                        title="Service Officer",
                    )
                )

            for dept_spec in spec["departments"]:
                department = Department(
                    office_id=office.id,
                    name=dept_spec["name"],
                    description=dept_spec["description"],
                )
                db.add(department)
                db.flush()
                for svc in dept_spec["services"]:
                    service = Service(
                        department_id=department.id,
                        code=svc["code"],
                        name=svc["name"],
                        description=svc["description"],
                        average_service_min=svc["average_service_min"],
                    )
                    service.documents = svc["documents"]
                    db.add(service)
                    db.flush()
                    services_by_code[svc["code"]] = service
                    for number in svc["counters"]:
                        counter = counter_by_number.get(number)
                        if counter is not None:
                            db.add(CounterService(counter_id=counter.id, service_id=service.id))

            db.add_all(
                [
                    PriorityRule(
                        office_id=office.id,
                        name="Senior citizens",
                        description="Citizens aged 60+ receive a queue priority boost.",
                        required_tags="senior",
                        boost=10,
                    ),
                    PriorityRule(
                        office_id=office.id,
                        name="Persons with disability",
                        description="Differently-abled citizens receive a queue priority boost.",
                        required_tags="disability",
                        boost=15,
                    ),
                    PriorityRule(
                        office_id=office.id,
                        name="Pregnant women",
                        description="Pregnant citizens receive a queue priority boost.",
                        required_tags="pregnant",
                        boost=12,
                    ),
                ]
            )
            db.flush()
        db.flush()

        # ---- Historical demo data --------------------------------------
        history = _seed_history(db, services_by_code)
        db.commit()
        print("Seeded DEMO data:")
        print(f"  offices={len(OFFICES)} services={len(services_by_code)}")
        print(f"  queue snapshots={history['snapshots']} service records={history['services']} historical tokens={history['tokens']}")
        print("Demo credentials (all share the same password):")
        print(f"  admin@queueless.demo  / {DEMO_PASSWORD}")
        print(f"  staff@queueless.demo  / {DEMO_PASSWORD}")
        print(f"  citizen@queueless.demo / {DEMO_PASSWORD}")
    finally:
        db.close()


def _seed_history(db, services_by_code) -> dict:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    days = 21
    snapshots: list[dict] = []
    service_records: list[dict] = []
    tokens: list[Token] = []

    for code, service in services_by_code.items():
        department = db.get(Department, service.department_id)
        office_id = department.office_id
        base_volume = 26 if "income" in code else 18
        sequence = db.scalar(
            select(TokenSequence).where(
                TokenSequence.office_id == office_id, TokenSequence.service_id == service.id
            )
        )
        if sequence is None:
            sequence = TokenSequence(office_id=office_id, service_id=service.id, next_number=1)
            db.add(sequence)
            db.flush()

        for day_offset in range(days, 0, -1):
            day = now - timedelta(days=day_offset)
            day_weight = DAY_WEIGHTS.get(day.weekday(), 0.0)
            if day_weight == 0:
                for hour_index in range(len(HOUR_WEIGHTS)):
                    snapshots.append(
                        {
                            "office_id": office_id,
                            "service_id": service.id,
                            "captured_at": day.replace(hour=9 + hour_index),
                            "hour_of_day": 9 + hour_index,
                            "day_of_week": day.weekday(),
                            "queue_length": 0,
                            "active_counters": 0,
                            "avg_service_min": 0,
                            "avg_wait_min": 0,
                            "origin": DataOrigin.DEMO.value,
                        }
                    )
                continue

            active = 4 if office_id == 1 else 3
            for hour_index, weight in enumerate(HOUR_WEIGHTS):
                captured = day.replace(hour=9 + hour_index)
                demand = base_volume * weight * day_weight
                queue_length = max(0, int(random.gauss(demand, demand * 0.18)))
                avg_service = max(3.5, random.gauss(service.average_service_min, 1.1))
                throughput = max(1, active) * (60 / avg_service)
                avg_wait = queue_length / throughput * 60 if throughput else 0
                avg_wait = max(0, random.gauss(avg_wait, max(1, avg_wait * 0.15)))
                snapshots.append(
                    {
                        "office_id": office_id,
                        "service_id": service.id,
                        "captured_at": captured,
                        "hour_of_day": 9 + hour_index,
                        "day_of_week": day.weekday(),
                        "queue_length": queue_length,
                        "active_counters": active,
                        "avg_service_min": round(avg_service, 1),
                        "avg_wait_min": round(avg_wait, 1),
                        "queue_speed_min": round(avg_service / max(1, active), 2),
                        "no_show_rate": round(random.uniform(0.02, 0.12), 3),
                        "priority_load": int(queue_length * random.uniform(0.05, 0.2)),
                        "origin": DataOrigin.DEMO.value,
                    }
                )

                for _ in range(min(int(throughput), 6)):
                    started = captured + timedelta(minutes=random.randint(0, 55))
                    # Embed a genuine, learnable relationship so the Phase 5 model
                    # can recover real structure: busier hours and deeper queues
                    # take measurably longer, plus individual variation.
                    pressure = queue_length / max(1, active)
                    hour_stress = 1.0 + 0.14 * (weight - 1.0)
                    load_stress = 1.0 + 0.035 * min(pressure, 10.0)
                    weekday_stress = 1.06 if day.weekday() == 0 else 1.0
                    expected = service.average_service_min * hour_stress * load_stress * weekday_stress
                    duration = max(2.0, random.gauss(expected, expected * 0.12))
                    service_records.append(
                        {
                            "office_id": office_id,
                            "service_id": service.id,
                            "duration_min": round(duration, 2),
                            "started_at": started,
                            "completed_at": started + timedelta(minutes=duration),
                            "origin": DataOrigin.DEMO.value,
                        }
                    )

            daily_tokens = int(base_volume * day_weight * 1.2)
            for _ in range(max(0, daily_tokens)):
                number = sequence.next_number
                sequence.next_number += 1
                created = day.replace(
                    hour=random.randint(9, 16),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                )
                served = created + timedelta(minutes=max(2, random.gauss(22, 9)))
                completed = served + timedelta(minutes=max(2, random.gauss(service.average_service_min, 1.4)))
                token = Token(
                    reference=f"demo-{service.code}-{number}",
                    number=number,
                    label=f"Q-{number:03d}",
                    office_id=office_id,
                    service_id=service.id,
                    status=TokenStatus.COMPLETED.value,
                    created_at=created,
                    called_at=served,
                    started_at=served,
                    completed_at=completed,
                    fairness_score=round(random.uniform(82, 100), 1),
                    events=[
                        TokenEvent(from_status="", to_status=TokenStatus.CREATED.value, note="Demo historical token", actor_role="SYSTEM", created_at=created),
                        TokenEvent(from_status=TokenStatus.WAITING.value, to_status=TokenStatus.SERVING.value, note="Demo service started", actor_role="STAFF", created_at=served),
                        TokenEvent(from_status=TokenStatus.SERVING.value, to_status=TokenStatus.COMPLETED.value, note="Demo service completed", actor_role="STAFF", created_at=completed),
                    ],
                )
                tokens.append(token)

    if snapshots:
        db.bulk_insert_mappings(QueueSnapshot, snapshots)
    if service_records:
        db.bulk_insert_mappings(ServiceTimeRecord, service_records)
    db.add_all(tokens)
    db.flush()

    return {
        "snapshots": len(snapshots),
        "services": len(service_records),
        "tokens": len(tokens),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed QueueLess with labelled demo data.")
    parser.add_argument("--force", action="store_true", help="Delete existing data first.")
    args = parser.parse_args()
    seed(force=args.force)


if __name__ == "__main__":
    main()
