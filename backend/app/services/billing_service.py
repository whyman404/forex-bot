"""Billing use cases — Stripe Checkout, Customer Portal, webhooks, invoices.

Atlas Goro — webhooks are the single point of truth for entitlement state.
Frontend redirect after Checkout = nice-to-have UX; the entitlement flip
happens when Stripe POSTs `checkout.session.completed` (or `invoice.paid`)
back to us.

Key invariants:
  1. Webhook signature verified BEFORE we touch the DB.
  2. `stripe_events.stripe_event_id` is a UNIQUE constraint — race-safe
     idempotency. Insert first; if INSERT raises, we skip the dispatch.
  3. Every state change → audit_log row in same transaction.
  4. Stripe SDK is wrapped — if `STRIPE_API_KEY` is empty or starts with
     "fake_" we operate in offline mode (no network) so tests don't need
     a live key.

Plans (price IDs resolved from settings via plan_code):
  - trial         (14-day free, automatic; no Stripe Price)
  - pro_monthly   $29 / month → STRIPE_PRICE_PRO_MONTHLY
  - pro_yearly    $290 / year → STRIPE_PRICE_PRO_YEARLY
  - lifetime      $990 one-time → STRIPE_PRICE_LIFETIME
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    BillingPlanUnknownError,
    BillingStripeError,
    BillingWebhookSignatureError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.middleware.audit import record_audit
from app.models.invoice import Invoice
from app.models.stripe_event import StripeEvent
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import (
    BillingMePublic,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalRequest,
    CustomerPortalResponse,
    InvoicePublic,
    PlanCode,
    PlanDescriptor,
    PlansResponse,
    SubscriptionPublic,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stripe SDK wrapper — tolerate missing key in dev/test
# ---------------------------------------------------------------------------


class StripeAdapter:
    """Thin layer over stripe-python.

    Offline mode (no API key, or fake_ prefix) returns canned responses.
    """

    def __init__(self, api_key: str) -> None:
        self.offline = (not api_key) or api_key.startswith(("fake_", "sk_test_fake"))
        self._api_key = api_key
        if not self.offline:
            try:
                import stripe

                stripe.api_key = api_key
                self._stripe = stripe
            except Exception as exc:  # noqa: BLE001
                logger.warning("stripe_sdk_unavailable", err=str(exc))
                self.offline = True
                self._stripe = None
        else:
            self._stripe = None

    # ---- read helpers ---------------------------------------------------

    @property
    def sdk(self) -> Any:
        return self._stripe

    # ---- mutations ------------------------------------------------------

    def create_customer(self, *, email: str, metadata: dict[str, str]) -> str:
        if self.offline:
            return f"cus_fake_{metadata.get('user_id', 'xxx')[:8]}"
        try:
            result = self._stripe.Customer.create(email=email, metadata=metadata)
            return result["id"]
        except Exception as exc:  # noqa: BLE001
            raise BillingStripeError(f"create_customer failed: {exc}") from exc

    def create_checkout_session(
        self,
        *,
        mode: str,
        price_id: str,
        customer_id: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        trial_days: int | None = None,
    ) -> dict[str, Any]:
        if self.offline:
            sid = f"cs_fake_{metadata.get('user_id', 'xxx')[:8]}"
            return {"id": sid, "url": f"{success_url}?session_id={sid}&offline=1"}
        try:
            kwargs: dict[str, Any] = {
                "mode": mode,
                "customer": customer_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": metadata,
            }
            if mode == "subscription" and trial_days:
                kwargs["subscription_data"] = {"trial_period_days": trial_days}
            session = self._stripe.checkout.Session.create(**kwargs)
            return {"id": session["id"], "url": session["url"]}
        except Exception as exc:  # noqa: BLE001
            raise BillingStripeError(f"create_checkout_session failed: {exc}") from exc

    def create_portal_session(self, *, customer_id: str, return_url: str) -> str:
        if self.offline:
            return f"{return_url}?portal=offline&cust={customer_id}"
        try:
            session = self._stripe.billing_portal.Session.create(
                customer=customer_id, return_url=return_url
            )
            return session["url"]
        except Exception as exc:  # noqa: BLE001
            raise BillingStripeError(f"create_portal_session failed: {exc}") from exc

    # ---- webhook verification ------------------------------------------

    def construct_event(self, payload: bytes, sig_header: str, secret: str) -> dict[str, Any]:
        if self.offline:
            # In offline mode we still want tests to exercise dispatch — accept
            # an unsigned JSON body when secret is empty/fake, else reject.
            if not secret or secret.startswith("fake_"):
                import json

                try:
                    return json.loads(payload.decode())
                except Exception as exc:  # noqa: BLE001
                    raise BillingWebhookSignatureError(f"bad json: {exc}") from exc
            raise BillingWebhookSignatureError("offline Stripe + real secret")
        try:
            return self._stripe.Webhook.construct_event(payload, sig_header, secret)
        except Exception as exc:  # noqa: BLE001
            raise BillingWebhookSignatureError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Plan catalog — single source of truth (frontend reads /billing/plans)
# ---------------------------------------------------------------------------


def _plan_catalog() -> list[PlanDescriptor]:
    settings = get_settings()
    return [
        PlanDescriptor(
            code="trial",
            name="14-Day Free Trial",
            price_cents=0,
            interval="trial",
            trial_days=settings.stripe_trial_days,
            description="Try all Pro features free for 14 days. No card required.",
            features=[
                "All strategies (paper trading)",
                "1 strategy instance",
                "Up to 5 backtests per day",
                "Email support",
            ],
        ),
        PlanDescriptor(
            code="pro_monthly",
            name="Pro Monthly",
            price_cents=2900,
            interval="month",
            description="Full live trading access, billed monthly.",
            features=[
                "Live trading (after gate checks)",
                "Unlimited strategy instances",
                "Unlimited backtests",
                "Priority support",
                "API access",
            ],
            stripe_price_id=settings.stripe_price_pro_monthly
            or settings.stripe_price_id_pro_monthly,
        ),
        PlanDescriptor(
            code="pro_yearly",
            name="Pro Yearly",
            price_cents=29000,
            interval="year",
            description="Pro Monthly minus 2 months. Best value.",
            features=[
                "Everything in Pro Monthly",
                "2x higher rate limits",
                "Quarterly review call",
            ],
            stripe_price_id=settings.stripe_price_pro_yearly
            or settings.stripe_price_id_pro_yearly,
        ),
        PlanDescriptor(
            code="lifetime",
            name="Lifetime",
            price_cents=99000,
            interval="once",
            description="One-time payment. Locks in current pricing forever.",
            features=[
                "Everything in Pro Yearly",
                "Lifetime upgrades",
                "Founding-member badge",
            ],
            stripe_price_id=settings.stripe_price_lifetime,
        ),
    ]


def _resolve_price_id(plan_code: PlanCode) -> tuple[str | None, str]:
    """Return (price_id, mode) for a plan_code."""
    for p in _plan_catalog():
        if p.code == plan_code:
            mode = "payment" if p.interval == "once" else "subscription"
            if plan_code == "trial":
                return None, "trial"
            return p.stripe_price_id, mode
    raise BillingPlanUnknownError(f"plan_code={plan_code}")


# ---------------------------------------------------------------------------
# BillingService
# ---------------------------------------------------------------------------


class BillingService:
    """Service object — one per request, scoped to its AsyncSession."""

    def __init__(self, db: AsyncSession, *, adapter: StripeAdapter | None = None) -> None:
        self.db = db
        settings = get_settings()
        self.settings = settings
        self.adapter = adapter or StripeAdapter(settings.stripe_api_key)

    # =====================================================================
    # Read APIs
    # =====================================================================

    async def list_plans(self) -> PlansResponse:
        return PlansResponse(plans=_plan_catalog())

    async def get_billing_me(self, user_id: UUID) -> BillingMePublic:
        sub = await self._get_active_or_latest_subscription(user_id)
        invs = await self._list_recent_invoices(user_id, limit=10)
        sub_pub = (
            SubscriptionPublic.model_validate(sub)
            if sub is not None
            else SubscriptionPublic()
        )
        return BillingMePublic(
            subscription=sub_pub,
            invoices=[InvoicePublic.model_validate(i) for i in invs],
        )

    async def get_subscription(self, user_id: UUID) -> SubscriptionPublic:
        sub = await self._get_active_or_latest_subscription(user_id)
        if sub is None:
            return SubscriptionPublic()
        return SubscriptionPublic.model_validate(sub)

    async def _get_active_or_latest_subscription(
        self, user_id: UUID
    ) -> Subscription | None:
        # Prefer active/trialing rows; else latest by created_at.
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(desc(Subscription.created_at))
        )
        for s in result.scalars().all():
            return s
        return None

    async def _list_recent_invoices(self, user_id: UUID, *, limit: int) -> list[Invoice]:
        result = await self.db.execute(
            select(Invoice)
            .where(Invoice.user_id == user_id)
            .order_by(desc(Invoice.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get_user(self, user_id: UUID) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found", code="USER_NOT_FOUND")
        return user

    # =====================================================================
    # Customer creation (called on signup)
    # =====================================================================

    async def ensure_customer(self, user_id: UUID) -> str:
        """Create or fetch Stripe Customer ID for this user.

        Stores it on the (single) latest subscription row, or creates a
        'inactive/free' placeholder subscription if none exists.
        """
        user = await self._get_user(user_id)
        sub = await self._get_active_or_latest_subscription(user_id)
        if sub is not None and sub.stripe_customer_id:
            return sub.stripe_customer_id

        cust_id = self.adapter.create_customer(
            email=str(user.email), metadata={"user_id": str(user.id)}
        )

        if sub is None:
            sub = Subscription(
                user_id=user.id,
                plan="trial",
                status="trialing",
                stripe_customer_id=cust_id,
            )
            self.db.add(sub)
        else:
            sub.stripe_customer_id = cust_id

        await record_audit(
            self.db,
            action="billing.customer.created",
            actor_user_id=user.id,
            target_type="subscription",
            target_id=sub.id,
            payload={"stripe_customer_id": cust_id[:10] + "…"},
        )
        await self.db.commit()
        return cust_id

    # =====================================================================
    # Checkout
    # =====================================================================

    async def create_checkout_session(
        self, user_id: UUID, payload: CheckoutSessionRequest
    ) -> CheckoutSessionResponse:
        user = await self._get_user(user_id)
        price_id, mode = _resolve_price_id(payload.plan_code)

        # Round 4 — use `effective_frontend_url` so Stripe redirects work on
        # Railway even before the operator wires `FRONTEND_URL` (falls back
        # to RAILWAY_PUBLIC_DOMAIN). This is the only safe behavior: a 404
        # redirect from Stripe leaves the user staring at a broken success
        # page.
        front = self.settings.effective_frontend_url

        if payload.plan_code == "trial":
            # Trial doesn't go through Checkout — flip subscription directly.
            await self._start_trial(user)
            success = (
                str(payload.success_url)
                if payload.success_url
                else f"{front}/billing/success?plan=trial"
            )
            return CheckoutSessionResponse(url=success, session_id="trial-no-checkout")

        if not price_id:
            raise BillingPlanUnknownError(
                f"plan_code={payload.plan_code} has no STRIPE_PRICE_* configured"
            )

        customer_id = await self.ensure_customer(user_id)

        success_url = str(
            payload.success_url
            or f"{front}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
        )
        cancel_url = str(
            payload.cancel_url or f"{front}/billing/cancel"
        )

        sess = self.adapter.create_checkout_session(
            mode=mode,
            price_id=price_id,
            customer_id=customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id), "plan_code": payload.plan_code},
            trial_days=None,
        )

        await record_audit(
            self.db,
            action="billing.checkout.created",
            actor_user_id=user.id,
            target_type="checkout_session",
            payload={"plan_code": payload.plan_code, "session_id": sess["id"]},
        )
        await self.db.commit()
        return CheckoutSessionResponse(url=sess["url"], session_id=sess["id"])

    async def _start_trial(self, user: User) -> None:
        """Set/create a trialing subscription if user has no active one."""
        sub = await self._get_active_or_latest_subscription(user.id)
        if sub is not None and sub.status in {"trialing", "active"}:
            return
        if sub is None:
            sub = Subscription(user_id=user.id, plan="trial", status="trialing")
            self.db.add(sub)
        else:
            sub.plan = "trial"
            sub.status = "trialing"
        # Phase 2 — trial period is enforced application-side; record start date.
        sub.current_period_start = datetime.now(UTC)
        # Trial ends at now + N days; we keep period_end accurate.
        from datetime import timedelta

        sub.current_period_end = datetime.now(UTC) + timedelta(
            days=self.settings.stripe_trial_days
        )
        await record_audit(
            self.db,
            action="billing.trial.started",
            actor_user_id=user.id,
            target_type="subscription",
            target_id=sub.id,
        )
        await self.db.commit()

    # =====================================================================
    # Customer Portal
    # =====================================================================

    async def create_customer_portal(
        self, user_id: UUID, payload: CustomerPortalRequest | None = None
    ) -> CustomerPortalResponse:
        customer_id = await self.ensure_customer(user_id)
        return_url = str(
            (payload.return_url if payload else None)
            or f"{self.settings.effective_frontend_url}/billing"
        )
        url = self.adapter.create_portal_session(
            customer_id=customer_id, return_url=return_url
        )
        return CustomerPortalResponse(url=url)

    # =====================================================================
    # Webhook
    # =====================================================================

    async def handle_webhook(self, raw_body: bytes, signature_header: str) -> None:
        """Single entry-point for ALL Stripe events.

        Order:
          1. verify signature (raises 400)
          2. INSERT stripe_events (UNIQUE on stripe_event_id — race-safe)
          3. dispatch on event_type
          4. mark processed
        Any step 3 failure leaves processed_at NULL so Stripe's retry hits us
        again (we replay safely since we INSERT-or-skip and the side-effects
        are idempotent).
        """
        if not signature_header:
            raise BillingWebhookSignatureError("Missing Stripe-Signature header")

        event = self.adapter.construct_event(
            raw_body, signature_header, self.settings.stripe_webhook_secret
        )
        event_id = event.get("id")
        event_type = event.get("type", "")
        if not event_id or not event_type:
            raise BillingWebhookSignatureError("event missing id or type")

        # Race-safe insert. If another worker beat us, IntegrityError → skip.
        already_seen = False
        ev_row = StripeEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=event if isinstance(event, dict) else dict(event),
        )
        self.db.add(ev_row)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            already_seen = True

        if already_seen:
            logger.info("stripe_event_duplicate_skipped", event_id=event_id)
            return

        try:
            await self._dispatch_event(event_type, event)
            ev_row.processed_at = datetime.now(UTC)
            await self.db.commit()
        except AppError:
            await self.db.rollback()
            raise
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            logger.error("stripe_dispatch_failed", event_id=event_id, err=str(exc))
            # Leave processed_at NULL so Stripe re-delivers.
            raise BillingStripeError(f"dispatch {event_type} failed: {exc}") from exc

    async def _dispatch_event(self, event_type: str, event: dict[str, Any]) -> None:
        data = event.get("data", {}).get("object", {}) or {}
        if event_type == "checkout.session.completed":
            await self._on_checkout_completed(data)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
        }:
            await self._on_subscription_upsert(data)
        elif event_type == "customer.subscription.deleted":
            await self._on_subscription_deleted(data)
        elif event_type == "invoice.paid":
            await self._on_invoice_paid(data)
        elif event_type == "invoice.payment_failed":
            await self._on_invoice_failed(data)
        else:
            logger.info("stripe_event_unhandled", event_type=event_type)

    # ---- Event handlers --------------------------------------------------

    async def _resolve_user_from_event(
        self, data: dict[str, Any]
    ) -> User | None:
        """Try metadata.user_id, else stripe_customer_id → subscription row."""
        metadata = data.get("metadata") or {}
        user_id_str = metadata.get("user_id")
        if user_id_str:
            try:
                return await self._get_user(UUID(user_id_str))
            except (ValueError, NotFoundError):
                pass
        customer_id = data.get("customer")
        if customer_id:
            result = await self.db.execute(
                select(Subscription).where(
                    Subscription.stripe_customer_id == customer_id
                )
            )
            sub = result.scalars().first()
            if sub is not None:
                try:
                    return await self._get_user(sub.user_id)
                except NotFoundError:
                    return None
        return None

    async def _on_checkout_completed(self, data: dict[str, Any]) -> None:
        user = await self._resolve_user_from_event(data)
        if user is None:
            logger.warning("checkout_completed_unresolved", session_id=data.get("id"))
            return
        # If subscription mode, the subscription.created event will set details;
        # here just upsert the customer link.
        sub = await self._get_active_or_latest_subscription(user.id)
        customer_id = data.get("customer")
        if sub is None:
            sub = Subscription(
                user_id=user.id, plan="pro_monthly", status="incomplete",
                stripe_customer_id=customer_id,
            )
            self.db.add(sub)
        else:
            if customer_id and not sub.stripe_customer_id:
                sub.stripe_customer_id = customer_id

        # One-time payment ("lifetime"): mark active immediately.
        if data.get("mode") == "payment":
            metadata = data.get("metadata") or {}
            sub.plan = metadata.get("plan_code") or "lifetime"
            sub.status = "active"
            sub.current_period_start = datetime.now(UTC)
            sub.current_period_end = None  # lifetime never expires

        await record_audit(
            self.db,
            action="billing.checkout.completed",
            actor_user_id=user.id,
            target_type="subscription",
            target_id=sub.id,
            payload={"mode": data.get("mode"), "session_id": data.get("id")},
        )

    async def _on_subscription_upsert(self, data: dict[str, Any]) -> None:
        user = await self._resolve_user_from_event(data)
        if user is None:
            return
        stripe_sub_id = data.get("id")
        status = data.get("status", "incomplete")
        # Stripe sends UNIX epoch seconds for periods.
        cps = data.get("current_period_start")
        cpe = data.get("current_period_end")
        items = (data.get("items") or {}).get("data") or []
        price_id = (items[0].get("price") or {}).get("id") if items else None
        plan = self._plan_code_for_price(price_id)

        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_sub_id
            )
        )
        sub = result.scalars().first()
        if sub is None:
            sub = await self._get_active_or_latest_subscription(user.id)
        if sub is None:
            sub = Subscription(
                user_id=user.id, plan=plan or "pro_monthly", status=status,
                stripe_subscription_id=stripe_sub_id,
                stripe_customer_id=data.get("customer"),
            )
            self.db.add(sub)
        else:
            sub.stripe_subscription_id = stripe_sub_id
            if data.get("customer"):
                sub.stripe_customer_id = data.get("customer")
            if plan:
                sub.plan = plan
            sub.status = status
        if cps:
            sub.current_period_start = datetime.fromtimestamp(int(cps), tz=UTC)
        if cpe:
            sub.current_period_end = datetime.fromtimestamp(int(cpe), tz=UTC)
        if status == "canceled":
            sub.canceled_at = datetime.now(UTC)

        await record_audit(
            self.db,
            action="billing.subscription.upserted",
            actor_user_id=user.id,
            target_type="subscription",
            target_id=sub.id,
            payload={"status": status, "plan": sub.plan},
        )

    async def _on_subscription_deleted(self, data: dict[str, Any]) -> None:
        stripe_sub_id = data.get("id")
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_sub_id
            )
        )
        sub = result.scalars().first()
        if sub is None:
            return
        sub.status = "canceled"
        sub.canceled_at = datetime.now(UTC)
        await record_audit(
            self.db,
            action="billing.subscription.deleted",
            actor_user_id=sub.user_id,
            target_type="subscription",
            target_id=sub.id,
        )

    async def _on_invoice_paid(self, data: dict[str, Any]) -> None:
        user = await self._resolve_user_from_event(data)
        if user is None:
            return
        await self._upsert_invoice(user.id, data, status="paid")

    async def _on_invoice_failed(self, data: dict[str, Any]) -> None:
        user = await self._resolve_user_from_event(data)
        if user is None:
            return
        await self._upsert_invoice(user.id, data, status="open")
        # Queue billing_failed email.
        from app.services.email_service import EmailService

        try:
            await EmailService().send(
                to=str(user.email),
                template="billing_failed",
                context={"display_name": user.full_name or "Trader"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("billing_failed_email_skipped", err=str(exc))
        await record_audit(
            self.db,
            action="billing.invoice.failed",
            actor_user_id=user.id,
            target_type="invoice",
            payload={"stripe_invoice_id": data.get("id")},
        )

    async def _upsert_invoice(
        self, user_id: UUID, data: dict[str, Any], *, status: str
    ) -> None:
        stripe_inv_id = data.get("id")
        if not stripe_inv_id:
            return
        result = await self.db.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_inv_id)
        )
        inv = result.scalars().first()
        amount = int(data.get("amount_paid", data.get("amount_due", 0)) or 0)
        currency = (data.get("currency") or "usd").lower()[:3]
        paid_at = None
        if status == "paid" and data.get("status_transitions", {}).get("paid_at"):
            paid_at = datetime.fromtimestamp(
                int(data["status_transitions"]["paid_at"]), tz=UTC
            )
        hosted_url = data.get("hosted_invoice_url")

        if inv is None:
            inv = Invoice(
                user_id=user_id,
                stripe_invoice_id=stripe_inv_id,
                amount_cents=amount,
                currency=currency,
                status=status,
                paid_at=paid_at,
                hosted_invoice_url=hosted_url,
            )
            self.db.add(inv)
        else:
            inv.amount_cents = amount
            inv.currency = currency
            inv.status = status
            if paid_at:
                inv.paid_at = paid_at
            if hosted_url:
                inv.hosted_invoice_url = hosted_url

    @staticmethod
    def _plan_code_for_price(price_id: str | None) -> str | None:
        if not price_id:
            return None
        s = get_settings()
        if price_id == (s.stripe_price_pro_monthly or s.stripe_price_id_pro_monthly):
            return "pro_monthly"
        if price_id == (s.stripe_price_pro_yearly or s.stripe_price_id_pro_yearly):
            return "pro_yearly"
        if price_id == s.stripe_price_lifetime:
            return "lifetime"
        return None
