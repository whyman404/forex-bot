"""Error contract — single error response shape across the API.

See: docs/api/error-contract.md
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Body of an error response. Keep stable — clients depend on it."""

    code: str = Field(description="Stable machine-readable error code (e.g. AUTH_INVALID_CREDENTIALS)")
    message: str = Field(description="Human-readable summary, safe to display.")
    details: dict[str, Any] | None = Field(default=None, description="Optional structured context.")
    trace_id: str | None = Field(default=None, alias="traceId", description="Correlate with logs/traces.")

    model_config = {"populate_by_name": True}


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Base application error. Always carries an HTTP status + stable code."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Unexpected error."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message:
            self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details
        super().__init__(self.message)


# ---- Concrete error classes (per-namespace) ---------------------------------


class ValidationFailedError(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "Request validation failed."


class AuthInvalidCredentialsError(AppError):
    status_code = 401
    code = "AUTH_INVALID_CREDENTIALS"
    message = "Invalid email or password."


class AuthTokenExpiredError(AppError):
    status_code = 401
    code = "AUTH_TOKEN_EXPIRED"
    message = "Access token expired."


class AuthTokenInvalidError(AppError):
    status_code = 401
    code = "AUTH_TOKEN_INVALID"
    message = "Token signature or claims invalid."


class AuthMfaRequiredError(AppError):
    status_code = 401
    code = "AUTH_MFA_REQUIRED"
    message = "Multi-factor authentication is required for this action."


class AuthMfaInvalidError(AppError):
    status_code = 401
    code = "AUTH_MFA_INVALID"
    message = "Invalid MFA code."


class AuthEmailNotVerifiedError(AppError):
    status_code = 403
    code = "AUTH_EMAIL_NOT_VERIFIED"
    message = "Email address not verified."


class ForbiddenError(AppError):
    status_code = 403
    code = "AUTH_FORBIDDEN"
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource conflict."


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests."


class BillingPaymentRequiredError(AppError):
    status_code = 402
    code = "BILLING_PAYMENT_REQUIRED"
    message = "Active subscription required."


class BillingWebhookSignatureError(AppError):
    status_code = 400
    code = "BILLING_WEBHOOK_SIGNATURE"
    message = "Invalid Stripe webhook signature."


class BrokerConnectionError(AppError):
    status_code = 502
    code = "BROKER_CONNECTION_FAILED"
    message = "Could not connect to broker."


class BrokerInvalidCredentialsError(AppError):
    status_code = 400
    code = "BROKER_INVALID_CREDENTIALS"
    message = "Broker credentials are invalid."


class StrategyNotFoundError(AppError):
    status_code = 404
    code = "STRATEGY_NOT_FOUND"
    message = "Strategy code unknown."


class StrategyInstanceConflictError(AppError):
    status_code = 409
    code = "STRATEGY_INSTANCE_CONFLICT"
    message = "Cannot transition instance in current state."


class BacktestNotFoundError(AppError):
    status_code = 404
    code = "BACKTEST_NOT_FOUND"
    message = "Backtest not found."


class BacktestQueueFullError(AppError):
    status_code = 503
    code = "BACKTEST_QUEUE_FULL"
    message = "Backtest queue is full. Try later."


# ---- Phase 2 — billing / live / email / internal --------------------------


class BillingPlanUnknownError(AppError):
    status_code = 400
    code = "BILLING_PLAN_UNKNOWN"
    message = "Unknown billing plan code."


class BillingStripeError(AppError):
    status_code = 502
    code = "BILLING_STRIPE_ERROR"
    message = "Stripe API call failed."


class LiveGateFailedError(AppError):
    status_code = 403
    code = "LIVE_GATE_FAILED"
    message = "Cannot go live — gate checks failed."


class LiveConsentMissingError(AppError):
    status_code = 403
    code = "LIVE_CONSENT_MISSING"
    message = "Live trading agreement not signed for this strategy."


class StrategyInstanceLockedError(AppError):
    status_code = 409
    code = "STRATEGY_INSTANCE_LOCKED"
    message = "Cannot edit high-risk parameters while instance is live."


class InternalSignatureInvalidError(AppError):
    status_code = 401
    code = "INTERNAL_SIGNATURE_INVALID"
    message = "Internal HMAC signature invalid."


class EmailTokenInvalidError(AppError):
    status_code = 400
    code = "EMAIL_TOKEN_INVALID"
    message = "Verification token invalid or already used."


class EmailTokenExpiredError(AppError):
    status_code = 410
    code = "EMAIL_TOKEN_EXPIRED"
    message = "Verification token expired."


class TwoFactorRequiredError(AppError):
    status_code = 401
    code = "TWO_FACTOR_REQUIRED"
    message = "TOTP challenge required for this sensitive operation."
