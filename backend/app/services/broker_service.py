"""Broker account use cases — CRUD + connection test.

Credentials are envelope-encrypted via `app/core/encryption.py` (ADR-005).
The bytea layout in DB is compact: nonce(12) || encrypted_dek || nonce_dek(12) || ciphertext.

For schema-fidelity with Mnemosyne's BrokerAccount columns
(`credentials_ciphertext`, `credentials_nonce`, `credentials_key_version`)
we pack [nonce_dek + encrypted_dek + nonce_payload(12) + ciphertext] into
credentials_ciphertext, and store nonce_payload separately in credentials_nonce.

Layout in `credentials_ciphertext`:
  [u16 n_dek_nonce][u16 n_encrypted_dek] + dek_nonce + encrypted_dek + ciphertext
And `credentials_nonce` = nonce_payload (12 bytes).
"""

from __future__ import annotations

import json
import struct
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import EncryptedBlob, decrypt, encrypt
from app.core.errors import (
    BrokerConnectionError,
    ConflictError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.middleware.audit import record_audit
from app.models.broker_account import BrokerAccount
from app.schemas.broker import (
    BrokerAccountCreateRequest,
    BrokerAccountPublic,
    BrokerAccountUpdateRequest,
    BrokerConnectionTestResponse,
)

logger = get_logger(__name__)


def _pack_blob_for_column(blob: EncryptedBlob) -> tuple[bytes, bytes, int]:
    """Return (credentials_ciphertext, credentials_nonce, key_version)."""
    body = (
        struct.pack(">HH", len(blob.nonce_dek), len(blob.encrypted_dek))
        + blob.nonce_dek
        + blob.encrypted_dek
        + blob.ciphertext
    )
    return body, blob.nonce_payload, blob.key_version


def _unpack_blob_from_column(ciphertext_blob: bytes, nonce_payload: bytes, key_version: int) -> EncryptedBlob:
    header = struct.calcsize(">HH")
    n_dek_nonce, n_enc_dek = struct.unpack(">HH", ciphertext_blob[:header])
    off = header
    dek_nonce = ciphertext_blob[off : off + n_dek_nonce]
    off += n_dek_nonce
    encrypted_dek = ciphertext_blob[off : off + n_enc_dek]
    off += n_enc_dek
    real_ciphertext = ciphertext_blob[off:]
    return EncryptedBlob(
        ciphertext=real_ciphertext,
        nonce_payload=nonce_payload,
        encrypted_dek=encrypted_dek,
        nonce_dek=dek_nonce,
        key_version=key_version,
    )


class BrokerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---- CRUD ------------------------------------------------------------

    async def create(
        self, user_id: UUID, payload: BrokerAccountCreateRequest
    ) -> BrokerAccountPublic:
        plaintext = json.dumps(payload.credentials, separators=(",", ":")).encode()
        aad = f"user:{user_id}|broker:{payload.broker}".encode()
        blob = encrypt(plaintext, aad=aad)
        body, nonce_payload, kv = _pack_blob_for_column(blob)

        account = BrokerAccount(
            user_id=user_id,
            broker=payload.broker,
            account_label=payload.account_label,
            mt5_login=payload.mt5_login,
            mt5_server=payload.mt5_server,
            leverage=payload.leverage,
            account_currency=(payload.account_currency or None),
            credentials_ciphertext=body,
            credentials_nonce=nonce_payload,
            credentials_key_version=kv,
        )
        self.db.add(account)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError(
                "Broker account label already in use.",
                code="BROKER_LABEL_TAKEN",
                status_code=409,
            ) from exc

        await record_audit(
            self.db,
            action="broker_account.created",
            actor_user_id=user_id,
            target_type="broker_account",
            target_id=account.id,
            payload={"broker": payload.broker, "label": payload.account_label},
        )
        await self.db.commit()
        await self.db.refresh(account)
        return BrokerAccountPublic.model_validate(account)

    async def list_for_user(self, user_id: UUID) -> list[BrokerAccountPublic]:
        result = await self.db.execute(
            select(BrokerAccount)
            .where(
                BrokerAccount.user_id == user_id, BrokerAccount.deleted_at.is_(None)
            )
            .order_by(BrokerAccount.created_at.desc())
        )
        return [BrokerAccountPublic.model_validate(a) for a in result.scalars().all()]

    async def _own(self, user_id: UUID, account_id: UUID) -> BrokerAccount:
        result = await self.db.execute(
            select(BrokerAccount).where(
                BrokerAccount.id == account_id,
                BrokerAccount.user_id == user_id,
                BrokerAccount.deleted_at.is_(None),
            )
        )
        a = result.scalar_one_or_none()
        if a is None:
            raise NotFoundError(
                "Broker account not found",
                code="BROKER_ACCOUNT_NOT_FOUND",
                status_code=404,
            )
        return a

    async def update(
        self,
        user_id: UUID,
        account_id: UUID,
        payload: BrokerAccountUpdateRequest,
    ) -> BrokerAccountPublic:
        account = await self._own(user_id, account_id)
        if payload.account_label is not None:
            account.account_label = payload.account_label
        if payload.is_active is not None:
            account.is_active = payload.is_active
        if payload.credentials is not None:
            aad = f"user:{user_id}|broker:{account.broker}".encode()
            blob = encrypt(
                json.dumps(payload.credentials, separators=(",", ":")).encode(),
                aad=aad,
            )
            body, nonce_payload, kv = _pack_blob_for_column(blob)
            account.credentials_ciphertext = body
            account.credentials_nonce = nonce_payload
            account.credentials_key_version = kv
        await self.db.commit()
        await self.db.refresh(account)
        return BrokerAccountPublic.model_validate(account)

    async def delete(self, user_id: UUID, account_id: UUID) -> None:
        account = await self._own(user_id, account_id)
        # Soft-delete (preserve referential integrity for trades/instances)
        account.deleted_at = datetime.now(UTC)
        account.is_active = False
        await record_audit(
            self.db,
            action="broker_account.deleted",
            actor_user_id=user_id,
            target_type="broker_account",
            target_id=account.id,
        )
        await self.db.commit()

    # ---- Connection test (calls mt5-bridge stub) -------------------------

    def _decrypt_credentials(self, account: BrokerAccount) -> dict:
        blob = _unpack_blob_from_column(
            account.credentials_ciphertext,
            account.credentials_nonce,
            account.credentials_key_version,
        )
        aad = f"user:{account.user_id}|broker:{account.broker}".encode()
        plaintext = decrypt(blob, aad=aad)
        return json.loads(plaintext.decode())

    async def test_connection(
        self, user_id: UUID, account_id: UUID
    ) -> BrokerConnectionTestResponse:
        settings = get_settings()
        account = await self._own(user_id, account_id)

        # Resolve the bridge URL — env or default for dev compose.
        bridge_url = getattr(settings, "mt5_bridge_url", "") or "http://mt5-bridge-stub:9100"

        # Build payload — strip secret-y keys from log, but the bridge needs them.
        try:
            creds = self._decrypt_credentials(account)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "creds_decrypt_failed",
                account_id=str(account.id),
                err=str(exc),
            )
            raise BrokerConnectionError("Could not decrypt broker credentials.") from exc

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{bridge_url.rstrip('/')}/connection/test",
                    json={
                        "broker": account.broker,
                        "mt5_login": account.mt5_login,
                        "mt5_server": account.mt5_server,
                        "credentials": creds,
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "broker_bridge_unreachable",
                bridge_url=bridge_url,
                err=str(exc),
            )
            # Don't fail closed in MVP — return ok=false so UI can show message.
            return BrokerConnectionTestResponse(
                ok=False,
                broker=account.broker,
                account_id=account.id,
                latency_ms=int((time.perf_counter() - start) * 1000),
                detail="bridge unreachable (dev)",
            )

        latency = int((time.perf_counter() - start) * 1000)
        ok = resp.status_code == 200
        detail = None
        try:
            body = resp.json()
            ok = bool(body.get("ok", ok))
            detail = body.get("detail")
        except Exception:  # noqa: BLE001
            detail = f"status={resp.status_code}"

        # Update last_sync_at on success
        if ok:
            account.last_sync_at = datetime.now(UTC)
            await self.db.commit()

        return BrokerConnectionTestResponse(
            ok=ok,
            broker=account.broker,
            account_id=account.id,
            latency_ms=latency,
            detail=detail,
        )
