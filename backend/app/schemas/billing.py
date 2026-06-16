"""Billing / subscription schemas — Stripe-backed.

Atlas Goro — keep these stable; frontend pricing card binds to them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

PlanCode = Literal["trial", "pro_monthly", "pro_yearly", "lifetime"]
SubscriptionStatus = Literal[
    "inactive", "trialing", "active", "past_due", "canceled", "incomplete", "unpaid"
]


class CheckoutSessionRequest(BaseModel):
    """Front-end posts plan_code; back-end resolves to Stripe price_id.

    Optional success_url / cancel_url override defaults (FRONTEND_URL + /billing/...).
    """

    plan_code: PlanCode
    success_url: HttpUrl | None = None
    cancel_url: HttpUrl | None = None


class CheckoutSessionResponse(BaseModel):
    url: HttpUrl
    session_id: str


class CustomerPortalRequest(BaseModel):
    return_url: HttpUrl | None = None


class CustomerPortalResponse(BaseModel):
    url: HttpUrl


class SubscriptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    plan: PlanCode | Literal["free"] = "free"
    status: SubscriptionStatus = "inactive"
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    stripe_customer_id: str | None = None


class InvoicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stripe_invoice_id: str
    amount_cents: int
    currency: str
    status: str
    paid_at: datetime | None
    hosted_invoice_url: str | None
    created_at: datetime


class BillingMePublic(BaseModel):
    """Combined view: current subscription + recent invoices."""

    subscription: SubscriptionPublic
    invoices: list[InvoicePublic] = Field(default_factory=list)


class PlanDescriptor(BaseModel):
    code: PlanCode
    name: str
    price_cents: int
    currency: str = "usd"
    interval: Literal["once", "month", "year", "trial"]
    trial_days: int | None = None
    description: str
    features: list[str] = Field(default_factory=list)
    stripe_price_id: str | None = None


class PlansResponse(BaseModel):
    plans: list[PlanDescriptor]
