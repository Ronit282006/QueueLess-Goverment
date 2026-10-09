"""Train per-service prediction models and report accuracy.

Usage:
    python -m app.ml.train            # train every service
    python -m app.ml.train --service 1
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Service
from .model import train_service_model


def train_all(service_id: int | None = None) -> list[dict]:
    db = SessionLocal()
    results: list[dict] = []
    try:
        stmt = select(Service).order_by(Service.id)
        if service_id is not None:
            stmt = stmt.where(Service.id == service_id)
        for service in db.scalars(stmt):
            model = train_service_model(db, service.id)
            if model is None or model.metrics is None:
                results.append({"service_id": service.id, "name": service.name, "status": "insufficient_history"})
                continue
            m = model.metrics
            results.append(
                {
                    "service_id": service.id,
                    "name": service.name,
                    "status": "trained",
                    "samples": m.samples,
                    "mae_min": round(m.mae, 2),
                    "r2": round(m.r2, 3),
                    "top_feature": max(m.feature_importance.items(), key=lambda kv: kv[1])[0],
                }
            )
    finally:
        db.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Train QueueLess prediction models.")
    parser.add_argument("--service", type=int, default=None, help="Train a single service id")
    args = parser.parse_args()
    for row in train_all(args.service):
        if row["status"] == "insufficient_history":
            print(f"service {row['service_id']:>3}  {row['name']:<28} insufficient history")
        else:
            print(
                f"service {row['service_id']:>3}  {row['name']:<28} "
                f"samples={row['samples']:<5} MAE={row['mae_min']:<5}min R2={row['r2']}"
            )


if __name__ == "__main__":
    main()