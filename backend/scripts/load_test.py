"""Concurrent load test for the QueueLess token pipeline.

Generates tokens concurrently (the contention hotspot: atomic number
allocation) while a background task reads queue snapshots, then reports
throughput, latency percentiles and integrity checks.

Examples
--------
    # against a locally running server
    python scripts/load_test.py --base http://127.0.0.1:8000 --tokens 500 --concurrency 50

    # include the live poller and a priority-tag mix
    python scripts/load_test.py --tokens 1000 --concurrency 100 --poll
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx


async def discover_service(client: httpx.AsyncClient, base: str) -> tuple[int, int]:
    offices = (await client.get(f"{base}/api/offices")).json()
    service_id = offices[0]["departments"][0]["services"][0]["id"]
    return offices[0]["id"], service_id


async def create_one(client: httpx.AsyncClient, base: str, service_id: int, office_id: int) -> tuple[int, float, str]:
    started = time.perf_counter()
    response = await client.post(
        f"{base}/api/tokens",
        json={"service_id": service_id, "office_id": office_id},
    )
    elapsed = (time.perf_counter() - started) * 1000
    label = ""
    if response.status_code == 201:
        label = response.json().get("label", "")
    return response.status_code, elapsed, label


async def poll_loop(client: httpx.AsyncClient, base: str, service_id: int, office_id: int, stop: asyncio.Event, latencies: list) -> None:
    while not stop.is_set():
        started = time.perf_counter()
        try:
            await client.get(f"{base}/api/queue?service_id={service_id}&office_id={office_id}")
            latencies.append((time.perf_counter() - started) * 1000)
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.1)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[index]


async def run(args: argparse.Namespace) -> int:
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        office_id, service_id = await discover_service(client, args.base)
        if args.service_id:
            service_id = args.service_id
        print(f"target={args.base} office={office_id} service={service_id} tokens={args.tokens} concurrency={args.concurrency}")

        poll_latencies: list[float] = []
        stop = asyncio.Event()
        poller = asyncio.create_task(poll_loop(client, args.base, service_id, office_id, stop, poll_latencies)) if args.poll else None

        semaphore = asyncio.Semaphore(args.concurrency)
        latencies: list[float] = []
        statuses: dict[int, int] = {}
        labels: list[str] = []

        async def worker() -> None:
            async with semaphore:
                status, elapsed, label = await create_one(client, args.base, service_id, office_id)
                statuses[status] = statuses.get(status, 0) + 1
                latencies.append(elapsed)
                if label:
                    labels.append(label)

        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(args.tokens)))
        duration = time.perf_counter() - started

        if poller is not None:
            stop.set()
            await poller

        ok = statuses.get(201, 0)
        unique = len(set(labels))
        report = {
            "requests": args.tokens,
            "succeeded": ok,
            "statuses": {str(k): v for k, v in sorted(statuses.items())},
            "duration_s": round(duration, 3),
            "throughput_rps": round(ok / duration, 1),
            "latency_ms": {
                "p50": round(percentile(latencies, 0.50), 1),
                "p95": round(percentile(latencies, 0.95), 1),
                "p99": round(percentile(latencies, 0.99), 1),
                "max": round(max(latencies), 1) if latencies else 0.0,
                "mean": round(statistics.mean(latencies), 1) if latencies else 0.0,
            },
            "unique_labels": unique,
            "labels_are_unique": unique == ok,
        }
        if poll_latencies:
            report["queue_read_latency_ms"] = {
                "p50": round(percentile(poll_latencies, 0.50), 1),
                "p95": round(percentile(poll_latencies, 0.95), 1),
                "samples": len(poll_latencies),
            }

        print(json.dumps(report, indent=2))
        if statuses and set(statuses) - {201}:
            print("WARNING: non-201 responses observed")
            return 1
        if not report["labels_are_unique"]:
            print("FAIL: duplicate token numbers allocated under concurrency")
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="QueueLess concurrent load test")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--tokens", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--service-id", type=int, default=0)
    parser.add_argument("--poll", action="store_true", help="also read queue snapshots while generating load")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())