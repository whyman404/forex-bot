"""Email service — provider-agnostic adapter + RQ queue producer.

Atlas Goro — three providers:
  - ConsoleProvider (dev)  — logs subject + body; never raises.
  - SMTPProvider           — stdlib smtplib in a thread pool.
  - ResendProvider         — httpx.AsyncClient to https://api.resend.com.

Selection via EMAIL_PROVIDER env. If config invalid for the chosen provider
we fall back to ConsoleProvider with a structured warning — we'd rather log
than silently drop user signup flow.

Producer API: `await EmailService().send(to, template, context)`.
The producer just enqueues to Redis (`email_queue`). The worker (RQ) calls
back into the provider. If Redis is down, we send synchronously (fail-safe).
"""

from __future__ import annotations

import asyncio
import json
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Templates — keep tiny + inline. Real product: move to Jinja2 files.
# ---------------------------------------------------------------------------


def _template(name: str, ctx: dict[str, Any]) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    settings = get_settings()
    base_url = settings.frontend_url.rstrip("/")
    display_name = ctx.get("display_name") or ctx.get("email") or "Trader"

    if name == "verify_email":
        token = ctx.get("token", "")
        link = f"{base_url}/verify-email?token={token}"
        subject = "Verify your ForexBot email"
        text = (
            f"Hi {display_name},\n\n"
            f"Confirm your email by clicking:\n  {link}\n\n"
            f"This link expires in 24 hours.\n— ForexBot"
        )
        html = f"<p>Hi {display_name},</p><p><a href='{link}'>Confirm your email</a></p>"
        return subject, text, html

    if name == "reset_password":
        token = ctx.get("token", "")
        link = f"{base_url}/reset-password?token={token}"
        subject = "Reset your ForexBot password"
        text = (
            f"Hi {display_name},\n\n"
            f"Reset your password here:\n  {link}\n\n"
            f"This link expires in 1 hour. Ignore if not you.\n— ForexBot"
        )
        html = f"<p>Hi {display_name},</p><p><a href='{link}'>Reset password</a></p>"
        return subject, text, html

    if name == "welcome":
        subject = "Welcome to ForexBot"
        text = (
            f"Welcome, {display_name}! Your trial gives you 14 days of full Pro access.\n"
            f"Get started: {base_url}/dashboard\n— ForexBot"
        )
        html = f"<p>Welcome, {display_name}!</p>"
        return subject, text, html

    if name == "billing_failed":
        subject = "ForexBot — payment failed"
        text = (
            f"Hi {display_name},\n\n"
            f"Your latest charge failed. Update billing to keep live trading:\n"
            f"  {base_url}/billing\n— ForexBot"
        )
        html = f"<p>Hi {display_name},</p><p>Charge failed. <a href='{base_url}/billing'>Update billing</a>.</p>"
        return subject, text, html

    if name == "weekly_summary":
        pnl = ctx.get("net_pnl_cents", 0) / 100
        trades = ctx.get("trades_count", 0)
        subject = "ForexBot — your weekly summary"
        text = (
            f"Hi {display_name},\n\nThis week: net P&L ${pnl:.2f} across {trades} trades.\n"
            f"Details: {base_url}/dashboard\n— ForexBot"
        )
        html = f"<p>Net P&amp;L ${pnl:.2f} ({trades} trades).</p>"
        return subject, text, html

    if name == "kill_switch_triggered":
        instance = ctx.get("instance_label", "your strategy")
        subject = f"ForexBot — kill switch triggered ({instance})"
        text = (
            f"Hi {display_name},\n\n"
            f"The kill switch fired on {instance}. All positions closed.\n"
            f"Review: {base_url}/strategies\n— ForexBot"
        )
        html = f"<p>Kill switch fired on <b>{instance}</b>.</p>"
        return subject, text, html

    # Fallback
    subject = ctx.get("subject", "ForexBot")
    body = ctx.get("body", "")
    return subject, body, body


# ---------------------------------------------------------------------------
# Provider base + concretes
# ---------------------------------------------------------------------------


class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None: ...


class ConsoleProvider(EmailProvider):
    name = "console"

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        logger.info(
            "email_console",
            provider="console",
            to=to,
            subject=subject,
            body_preview=text[:140],
        )


class SMTPProvider(EmailProvider):
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, starttls: bool) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.starttls = starttls

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        def _send() -> None:
            with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                if self.starttls:
                    try:
                        s.starttls()
                    except Exception as exc:  # noqa: BLE001 — local SMTP may not support
                        logger.warning("smtp_starttls_failed", err=str(exc))
                if self.user and self.password:
                    s.login(self.user, self.password)
                s.send_message(msg)

        await asyncio.to_thread(_send)


class ResendProvider(EmailProvider):
    name = "resend"

    def __init__(self, api_key: str, sender: str) -> None:
        self.api_key = api_key
        self.sender = sender

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        payload: dict[str, Any] = {
            "from": self.sender,
            "to": [to],
            "subject": subject,
            "text": text,
        }
        if html:
            payload["html"] = html
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if r.status_code >= 400:
                raise RuntimeError(f"resend send failed: {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------------------
# Provider factory — never raises, falls back to ConsoleProvider
# ---------------------------------------------------------------------------


def get_provider() -> EmailProvider:
    settings = get_settings()
    name = (settings.email_provider or "console").lower()
    if name == "smtp":
        if not settings.smtp_host:
            logger.warning("email_provider_smtp_invalid", reason="missing_host")
            return ConsoleProvider()
        return SMTPProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.email_from or settings.smtp_from,
            starttls=settings.smtp_starttls,
        )
    if name == "resend":
        if not settings.resend_api_key:
            logger.warning("email_provider_resend_invalid", reason="missing_api_key")
            return ConsoleProvider()
        return ResendProvider(
            api_key=settings.resend_api_key, sender=settings.email_from
        )
    return ConsoleProvider()


# ---------------------------------------------------------------------------
# Public API — what services call
# ---------------------------------------------------------------------------


class EmailService:
    """Producer side — enqueues to Redis. Worker consumes."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def send(
        self,
        *,
        to: str,
        template: str,
        context: dict[str, Any] | None = None,
        redis: Any | None = None,
    ) -> None:
        """Enqueue an email job. If Redis unavailable, send synchronously."""
        ctx = context or {}
        ctx.setdefault("email", to)
        job = {"to": to, "template": template, "context": ctx}

        # Try Redis enqueue
        try:
            if redis is None:
                from redis.asyncio import Redis

                redis = Redis.from_url(str(self.settings.redis_url), decode_responses=True)
                await redis.lpush(self.settings.email_queue_name, json.dumps(job))
                await redis.aclose()
                logger.info("email_queued", to=to, template=template)
                return
            await redis.lpush(self.settings.email_queue_name, json.dumps(job))
            logger.info("email_queued", to=to, template=template)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("email_queue_failed_send_sync", err=str(exc))

        # Fallback synchronous send
        subject, text, html = _template(template, ctx)
        try:
            await get_provider().send(to=to, subject=subject, text=text, html=html)
        except Exception as exc:  # noqa: BLE001
            logger.error("email_sync_send_failed", template=template, err=str(exc))


async def render_and_send_now(to: str, template: str, context: dict[str, Any]) -> None:
    """Used by the worker — render template + invoke active provider."""
    subject, text, html = _template(template, context)
    await get_provider().send(to=to, subject=subject, text=text, html=html)
