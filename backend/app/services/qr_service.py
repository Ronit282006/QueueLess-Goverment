"""Secure QR references. The QR payload contains only an opaque token reference."""
from __future__ import annotations

import base64
import io

PREFIX = "queueless://token/"


def qr_payload(reference: str) -> str:
    return f"{PREFIX}{reference}"


def reference_from_payload(payload: str) -> str | None:
    payload = (payload or "").strip()
    if payload.startswith(PREFIX):
        return payload[len(PREFIX):] or None
    # Allow staff to scan a bare reference too.
    if payload and "/" not in payload:
        return payload
    return None


def qr_data_url(reference: str) -> str:
    import qrcode

    img = qrcode.make(qr_payload(reference))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"