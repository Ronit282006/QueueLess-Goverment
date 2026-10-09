"""WebSocket endpoints for live queue and token updates."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Token
from ..realtime import hub
from ..services import catalog_service, queue_service, token_view

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/queue")
async def ws_queue(websocket: WebSocket, office_id: int | None = None, service_id: int | None = None) -> None:
    with SessionLocal() as db:
        if service_id is None:
            service = catalog_service.first_service(db)
            service_id = service.id if service else 0
        context = catalog_service.service_with_context(db, service_id) if service_id else None
        resolved_office = office_id or (context["office"]["id"] if context and context["office"] else 0)
        initial = queue_service.snapshot(db, resolved_office, service_id) if service_id else None

    room = f"queue:{resolved_office}:{service_id}"
    await hub.connect(room, websocket)
    try:
        await websocket.send_json({"type": "queue.updated", "queue": initial})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(room, websocket)


@router.websocket("/ws/tokens/{reference}")
async def ws_token(websocket: WebSocket, reference: str) -> None:
    with SessionLocal() as db:
        token = db.scalar(select(Token).where(Token.reference == reference))
        initial = token_view.token_detail(db, token) if token else None
    await hub.connect(f"token:{reference}", websocket)
    try:
        await websocket.send_json({"type": "token.updated", "token": initial})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(f"token:{reference}", websocket)