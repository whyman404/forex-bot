"""Billing endpoints — Stripe Checkout + Customer Portal + webhook.

Atlas Goro — webhook is the ONLY unauthenticated endpoint here. Stripe signs
every event with `Stripe-Signature` (HMAC over the raw body). We verify
in BillingService.handle_webhook() BEFORE touching the DB.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BillingWebhookSignatureError, ErrorResponse
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.billing import (
    BillingMePublic,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalRequest,
    CustomerPortalResponse,
    PlansResponse,
)
from app.schemas.common import MessageResponse
from app.services.billing_service import BillingService

router = APIRouter()

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    402: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
}


@router.get(
    "/plans",
    response_model=PlansResponse,
    summary="List available billing plans",
    description="Public catalog: trial / pro_monthly / pro_yearly / lifetime.",
)
async def list_plans(db: AsyncSession = Depends(get_db)) -> PlansResponse:
    return await BillingService(db).list_plans()


@router.post(
    "/checkout-session",
    response_model=CheckoutSessionResponse,
    responses=ERROR_RESPONSES,
    summary="Start a Stripe Checkout session for the chosen plan_code",
)
async def create_checkout(
    payload: CheckoutSessionRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    return await BillingService(db).create_checkout_session(current.id, payload)


@router.post(
    "/customer-portal",
    response_model=CustomerPortalResponse,
    responses=ERROR_RESPONSES,
    summary="Open Stripe Customer Portal for managing payment methods",
)
async def open_portal(
    payload: CustomerPortalRequest | None = None,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerPortalResponse:
    return await BillingService(db).create_customer_portal(current.id, payload)


@router.post(
    "/webhook",
    name="billing_webhook",  # callable via request.url_for("billing_webhook")
    status_code=status.HTTP_200_OK,
    response_model=MessageResponse,
    responses=ERROR_RESPONSES,
    summary="Stripe webhook receiver (no auth — signature-verified)",
    include_in_schema=True,
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    raw = await request.body()
    if not stripe_signature:
        raise BillingWebhookSignatureError("Missing Stripe-Signature header")
    await BillingService(db).handle_webhook(raw, stripe_signature)
    return MessageResponse(message="ok")


@router.get(
    "/me",
    response_model=BillingMePublic,
    responses=ERROR_RESPONSES,
    summary="Current user's subscription + recent invoices",
)
async def get_billing_me(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingMePublic:
    return await BillingService(db).get_billing_me(current.id)
