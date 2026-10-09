"""Verify that Redis pub/sub relays realtime events across API instances.

Two independent Uvicorn processes are started on ports 8011 and 8012. A
WebSocket client connects to instance A while a token is created through
instance B. Because the two processes share only Redis, receiving the update on
instance A proves the horizontal-scaling path (spec section on scalability).

Run from the backend directory:  python scripts/multi_instance_check.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
PORTS = (8011, 8012)


def start_instance(port: int) -> subprocess.Popen:
    env = {**os.environ, "BACKGROUND_WORKERS_ENABLED": "false", "EMAIL_MODE": "log"}
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def wait_until_ready(client: httpx.AsyncClient, timeout: float = 40.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    for port in PORTS:
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"instance on port {port} did not become healthy")
            try:
                response = await client.get(f"http://127.0.0.1:{port}/api/health")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)


async def main() -> int:
    processes = [start_instance(port) for port in PORTS]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await wait_until_ready(client)
            print("both instances healthy")

            offices = (await client.get(f"http://127.0.0.1:{PORTS[0]}/api/offices")).json()
            service_id = offices[0]["departments"][0]["services"][0]["id"]
            office_id = offices[0]["id"]

            url = f"ws://127.0.0.1:{PORTS[0]}/ws/queue?service_id={service_id}&office_id={office_id}"
            async with websockets.connect(url) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert first["type"] == "queue.updated", first

                # Trigger the change through the *other* instance.
                created = await client.post(f"http://127.0.0.1:{PORTS[1]}/api/tokens", json={"service_id": service_id})
                assert created.status_code == 201, created.text
                reference = created.json()["reference"]

                update = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert update["type"] == "queue.updated", update
                assert update.get("service_id") == service_id, update

                # tidy up the probe token
                await client.post(
                    f"http://127.0.0.1:{PORTS[1]}/api/tokens/{reference}/transition",
                    json={"status": "CANCELLED"},
                )

            print("PASS: instance A received the queue update produced by instance B (Redis pub/sub relay)")
            return 0
    except Exception as exc:  # noqa: BLE001 - report any failure clearly
        print(f"FAIL: {exc}")
        return 1
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))