"""Self-contained HTML rendering for outgoing QueueLess notifications.

Notifications are composed and stored as plain text (tests, logs and the admin
notification list all read `Notification.body`). At delivery time the worker
attaches the HTML produced here as the `text/html` alternative part, so every
service — token confirmation, OTP, incident, staff welcome, queue updates —
sends one consistent, branded and formatted message without each call site
having to build markup itself.
"""
from __future__ import annotations

import html
import re

BRAND = "QueueLess"
BRAND_TAGLINE = "Public service, with less waiting"

# Inline CSS only: mail clients strip <style> blocks and external assets.
_ACCENT = "#1d4ed8"
_TEXT = "#0f172a"
_TEXT_MUTED = "#475569"
_LINE = "#e2e8f0"

_URL_RE = re.compile(r"https?://[^\s<>\"']+")
# "Token: Q-001" / "Response deadline: 2026-01-02 10:00 IST" style label rows.
_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /()'&+-]{1,48}):\s+(.+)$")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _inline(text: str) -> str:
    """Escape a line of plain text and turn bare URLs into links."""
    out: list[str] = []
    pos = 0
    for match in _URL_RE.finditer(text):
        raw = match.group(0)
        trimmed = raw.rstrip(".,)")
        out.append(_esc(text[pos:match.start()]))
        href = _esc(trimmed)
        out.append(f'<a href="{href}" style="color:{_ACCENT};word-break:break-all;">{href}</a>')
        pos = match.start() + len(trimmed)
    out.append(_esc(text[pos:]))
    return "".join(out)


def _split_blocks(body: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]


def _render_block(block: str) -> str:
    """Render one blank-line-delimited block, keeping prose/label rows in order."""
    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    parts: list[str] = []
    prose: list[str] = []
    rows: list[tuple[str, str]] = []

    def flush_prose() -> None:
        if prose:
            parts.append(
                f'<p style="margin:0 0 12px;color:{_TEXT_MUTED};">'
                + "<br />".join(_inline(line) for line in prose)
                + "</p>"
            )
            prose.clear()

    def flush_rows() -> None:
        if rows:
            trs = "".join(
                "<tr>"
                f'<th style="text-align:left;font-weight:600;color:{_TEXT};padding:8px 16px 8px 12px;'
                'vertical-align:top;white-space:nowrap;border-bottom:1px solid ' + _LINE + ';">'
                f"{_esc(label)}</th>"
                f'<td style="padding:8px 12px 8px 0;color:{_TEXT_MUTED};border-bottom:1px solid {_LINE};">'
                f"{_inline(value)}</td>"
                "</tr>"
                for label, value in rows
            )
            parts.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="border-collapse:collapse;margin:0 0 14px;font-size:15px;">'
                f"<tbody>{trs}</tbody></table>"
            )
            rows.clear()

    for line in lines:
        match = _LABEL_RE.match(line)
        if match:
            flush_prose()
            rows.append((match.group(1), match.group(2)))
        else:
            flush_rows()
            prose.append(line)
    flush_rows()
    flush_prose()
    return "".join(parts)


def render_email_html(subject: str, body: str) -> str:
    """Build the full HTML document for a notification."""
    content = "".join(
        f'<div style="margin:0 0 16px;">{_render_block(block)}</div>'
        for block in _split_blocks(body)
    )
    if not content:
        content = f"<p>{_inline(body)}</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>{_esc(subject)}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border:1px solid {_LINE};border-radius:14px;overflow:hidden;">
  <tr>
    <td style="background:{_ACCENT};padding:20px 28px;">
      <div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:0.02em;">{_esc(BRAND)}</div>
      <div style="font-size:12px;color:#dbeafe;letter-spacing:0.14em;text-transform:uppercase;margin-top:2px;">{_esc(BRAND_TAGLINE)}</div>
    </td>
  </tr>
  <tr>
    <td style="padding:26px 28px 6px;">
      <div style="font-size:11px;font-weight:700;color:{_ACCENT};letter-spacing:0.14em;text-transform:uppercase;">{_esc(BRAND)} notification</div>
      <h1 style="margin:8px 0 0;font-size:22px;line-height:1.3;color:{_TEXT};font-weight:700;">{_esc(subject)}</h1>
    </td>
  </tr>
  <tr>
    <td style="padding:14px 28px 4px;font-size:15px;line-height:1.6;color:{_TEXT_MUTED};">
      {content}
    </td>
  </tr>
  <tr>
    <td style="padding:10px 28px 24px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td style="border-top:1px solid {_LINE};padding-top:16px;font-size:12px;line-height:1.6;color:{_TEXT_MUTED};">
          This is an automated message from {_esc(BRAND)}, a government service queue management system.
          Predictions are estimates, not guarantees. Please do not reply to this email.
        </td></tr>
      </table>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""
