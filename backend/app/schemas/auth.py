"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    # Accept either `full_name` (canonical, matches DB column) or `display_name`
    # (legacy / what the Next.js form sends). Both populate the same attribute.
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    password: str = Field(min_length=12, max_length=128, description="Argon2-hashed server-side")
    full_name: str = Field(
        min_length=1,
        max_length=120,
        validation_alias=AliasChoices("full_name", "display_name"),
    )
    country: str = Field(default="TH", min_length=2, max_length=2)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)


class TotpEnrollResponse(BaseModel):
    secret: str = Field(description="Base32 TOTP secret — show once at enrollment")
    provisioning_uri: str = Field(description="otpauth:// URI for QR-code")


class TotpVerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")
