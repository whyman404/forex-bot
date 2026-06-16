"""Auth use cases — signup, login, token refresh, MFA enrollment.

Atlas Goro — auth flow is the most replayed code path. Every branch obvious.

Design:
- Refresh tokens are single-use; on use we add jti to denylist and mint a new pair.
- Access tokens are short (15m). On logout, jti added to denylist until exp.
- TOTP secret stored encrypted (envelope) with user.id as AAD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import EncryptedBlob, decrypt, encrypt
from app.core.errors import (
    AuthInvalidCredentialsError,
    AuthMfaInvalidError,
    AuthMfaRequiredError,
    AuthTokenInvalidError,
    ConflictError,
    EmailTokenExpiredError,
    EmailTokenInvalidError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    needs_rehash,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.core.tokens import generate_opaque_token, hash_token
from app.middleware.audit import record_audit
from app.models.email_token import EmailVerificationToken, PasswordResetToken
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenPair

logger = get_logger(__name__)


class AuthService:
    """Stateless service. One per request. Holds an AsyncSession."""

    def __init__(self, db: AsyncSession, *, redis=None) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.redis = redis  # Optional[redis.asyncio.Redis]

    # ---- Token issuance --------------------------------------------------

    def _mint_pair(self, user: User) -> TokenPair:
        settings = get_settings()
        access_token, _, _access_jti = create_token(
            str(user.id),
            "access",
            extra_claims={"role": user.role, "email": str(user.email)},
        )
        refresh_token, _, _refresh_jti = create_token(str(user.id), "refresh")
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_ttl_min * 60,
        )

    async def _revoke_jti(self, jti: str, ttl_seconds: int) -> None:
        if self.redis is None or not jti:
            return
        try:
            await self.redis.setex(f"jwt:revoked:{jti}", max(ttl_seconds, 1), "1")
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_revoke_failed", err=str(exc))

    # ---- Signup ----------------------------------------------------------

    async def signup(self, payload: SignupRequest) -> TokenPair:
        existing = await self.db.execute(
            select(User).where(User.email == payload.email, User.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(
                "Email already registered.", code="AUTH_EMAIL_TAKEN", status_code=409
            )

        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            country=(payload.country or "TH").upper(),
        )
        self.db.add(user)
        try:
            await self.db.flush()  # need user.id
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError(
                "Email already registered.", code="AUTH_EMAIL_TAKEN", status_code=409
            ) from exc

        # Email verification token (single-use, 24h)
        raw_token = generate_opaque_token()
        evt = EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        self.db.add(evt)

        try:
            await record_audit(
                self.db,
                action="auth.signup",
                actor_user_id=user.id,
                target_type="user",
                target_id=user.id,
                payload={"email": str(user.email)},
            )
        except Exception as exc:  # noqa: BLE001 — never block signup on audit
            logger.warning("audit_signup_failed", err=str(exc))

        await self.db.commit()
        await self.db.refresh(user)

        # Enqueue verify_email + welcome (best-effort)
        try:
            from app.services.billing_service import BillingService
            from app.services.email_service import EmailService

            email_svc = EmailService()
            await email_svc.send(
                to=str(user.email),
                template="verify_email",
                context={"display_name": user.full_name, "token": raw_token},
                redis=self.redis,
            )
            await email_svc.send(
                to=str(user.email),
                template="welcome",
                context={"display_name": user.full_name},
                redis=self.redis,
            )
            # Best-effort Stripe customer creation
            try:
                await BillingService(self.db).ensure_customer(user.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("stripe_customer_create_skipped", err=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("signup_post_hooks_failed", err=str(exc))

        return self._mint_pair(user)

    # ---- Login -----------------------------------------------------------

    async def login(self, payload: LoginRequest, *, ip: str | None = None) -> TokenPair:
        result = await self.db.execute(
            select(User).where(User.email == payload.email, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            # constant-time-ish — always run a hash to flatten timing signal.
            if user is None:
                _ = hash_password("dummy-noop-password-to-flatten-timing")
            raise AuthInvalidCredentialsError()

        # TOTP gate (if enrolled)
        if user.totp_secret is not None:
            if not payload.totp_code:
                raise AuthMfaRequiredError()
            try:
                secret = decrypt(
                    self._decode_totp_blob(user.totp_secret), aad=str(user.id).encode()
                ).decode()
            except Exception as exc:  # noqa: BLE001
                logger.error("totp_decrypt_failed", user_id=str(user.id), err=str(exc))
                raise AuthMfaInvalidError() from exc
            if not verify_totp(secret, payload.totp_code):
                raise AuthMfaInvalidError()

        # Rehash on outdated params (silent upgrade)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)

        try:
            await record_audit(
                self.db,
                action="auth.login",
                actor_user_id=user.id,
                target_type="user",
                target_id=user.id,
                payload={"ip": ip},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_login_failed", err=str(exc))

        await self.db.commit()
        return self._mint_pair(user)

    # ---- Refresh ---------------------------------------------------------

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except JWTError as exc:
            raise AuthTokenInvalidError(str(exc)) from exc

        jti = payload.get("jti")
        if self.redis is not None and jti:
            try:
                if await self.redis.exists(f"jwt:revoked:{jti}"):
                    raise AuthTokenInvalidError("Refresh token revoked")
            except AuthTokenInvalidError:
                raise
            except Exception as exc:  # noqa: BLE001 — fail open
                logger.warning("redis_check_failed", err=str(exc))

        try:
            user_id = UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise AuthTokenInvalidError("Invalid subject") from exc

        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise AuthTokenInvalidError("User no longer active")

        # Rotate: revoke old jti until its natural exp.
        exp = int(payload.get("exp", 0))
        ttl = max(exp - int(datetime.now(UTC).timestamp()), 1)
        await self._revoke_jti(jti or "", ttl)

        return self._mint_pair(user)

    # ---- Logout ----------------------------------------------------------

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except JWTError:
            return  # tolerate noop on bad token

        jti = payload.get("jti")
        if not jti:
            return
        exp = int(payload.get("exp", 0))
        ttl = max(exp - int(datetime.now(UTC).timestamp()), 1)
        await self._revoke_jti(jti, ttl)

    # ---- Email verify / reset (Phase 2 — fully wired) --------------------

    async def verify_email(self, token: str) -> None:
        digest = hash_token(token)
        result = await self.db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == digest
            )
        )
        evt = result.scalar_one_or_none()
        if evt is None or evt.used_at is not None:
            raise EmailTokenInvalidError()
        if evt.expires_at < datetime.now(UTC):
            raise EmailTokenExpiredError()

        user = await self.db.get(User, evt.user_id)
        if user is None or user.deleted_at is not None:
            raise EmailTokenInvalidError("User disabled")

        user.email_verified_at = datetime.now(UTC)
        evt.used_at = datetime.now(UTC)
        await record_audit(
            self.db,
            action="auth.email.verified",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
        )
        await self.db.commit()

    async def request_password_reset(self, email: str) -> None:
        """Always silent (no enumeration). Generate + email if user exists."""
        result = await self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            logger.info("password_reset_requested_unknown_email")
            return

        raw_token = generate_opaque_token()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.db.add(prt)
        await record_audit(
            self.db,
            action="auth.password.reset_requested",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
        )
        await self.db.commit()

        try:
            from app.services.email_service import EmailService

            await EmailService().send(
                to=str(user.email),
                template="reset_password",
                context={"display_name": user.full_name, "token": raw_token},
                redis=self.redis,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("password_reset_email_failed", err=str(exc))

    async def reset_password(self, token: str, new_password: str) -> None:
        digest = hash_token(token)
        result = await self.db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == digest)
        )
        prt = result.scalar_one_or_none()
        if prt is None or prt.used_at is not None:
            raise EmailTokenInvalidError()
        if prt.expires_at < datetime.now(UTC):
            raise EmailTokenExpiredError()

        user = await self.db.get(User, prt.user_id)
        if user is None or user.deleted_at is not None:
            raise EmailTokenInvalidError("User disabled")

        user.password_hash = hash_password(new_password)
        prt.used_at = datetime.now(UTC)
        await record_audit(
            self.db,
            action="auth.password.reset",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
        )
        await self.db.commit()

    # ---- TOTP ------------------------------------------------------------

    async def enroll_totp(self, user_id: str) -> tuple[str, str]:
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id), User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise AuthTokenInvalidError("User not found")

        secret = generate_totp_secret()
        blob = encrypt(secret.encode(), aad=str(user.id).encode())
        user.totp_secret = self._encode_totp_blob(blob)
        await self.db.commit()

        uri = totp_provisioning_uri(secret, account_name=str(user.email))
        return secret, uri

    async def verify_totp(self, user_id: str, code: str) -> None:
        result = await self.db.execute(
            select(User).where(User.id == UUID(user_id), User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if user is None or user.totp_secret is None:
            raise AuthMfaInvalidError()
        try:
            secret = decrypt(
                self._decode_totp_blob(user.totp_secret), aad=str(user.id).encode()
            ).decode()
        except Exception as exc:  # noqa: BLE001
            raise AuthMfaInvalidError() from exc
        if not verify_totp(secret, code):
            raise AuthMfaInvalidError()

        await record_audit(
            self.db,
            action="auth.totp.verified",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
        )
        await self.db.commit()

    # ---- TOTP blob encoding (compact for single bytea column) ------------

    @staticmethod
    def _encode_totp_blob(blob: EncryptedBlob) -> bytes:
        """Pack EncryptedBlob into a single bytea."""
        import struct

        # Layout: [u8 key_version][u16 n_payload][u16 n_dek_nonce][u16 n_cipher][u16 n_dek]
        # + nonce_payload + nonce_dek + ciphertext + encrypted_dek
        return (
            struct.pack(
                ">BHHHH",
                blob.key_version & 0xFF,
                len(blob.nonce_payload),
                len(blob.nonce_dek),
                len(blob.ciphertext),
                len(blob.encrypted_dek),
            )
            + blob.nonce_payload
            + blob.nonce_dek
            + blob.ciphertext
            + blob.encrypted_dek
        )

    @staticmethod
    def _decode_totp_blob(data: bytes) -> EncryptedBlob:
        import struct

        header_size = struct.calcsize(">BHHHH")
        key_version, n_payload, n_dek_nonce, n_cipher, n_dek = struct.unpack(
            ">BHHHH", data[:header_size]
        )
        off = header_size
        nonce_payload = data[off : off + n_payload]
        off += n_payload
        nonce_dek = data[off : off + n_dek_nonce]
        off += n_dek_nonce
        ciphertext = data[off : off + n_cipher]
        off += n_cipher
        encrypted_dek = data[off : off + n_dek]
        return EncryptedBlob(
            ciphertext=ciphertext,
            nonce_payload=nonce_payload,
            encrypted_dek=encrypted_dek,
            nonce_dek=nonce_dek,
            key_version=key_version,
        )
