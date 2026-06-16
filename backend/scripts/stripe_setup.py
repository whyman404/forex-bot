"""Stripe Product/Price provisioner.

Atlas Goro — idempotent CLI: creates the four plan Prices in Stripe if they
don't already exist, then prints the env block to paste into `.env`.

Usage:
    STRIPE_API_KEY=sk_test_... python -m scripts.stripe_setup

Matches: trial (no Price), pro_monthly $29/mo, pro_yearly $290/yr,
lifetime $990 one-time. Currency: USD.

Idempotency:
  * We look up Products by `metadata.code` (forexbot-pro / forexbot-lifetime).
  * For each Price we want, search Stripe with matching product + unit_amount
    + interval; if found, reuse; else create.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _get_stripe(api_key: str) -> Any:
    try:
        import stripe
    except ImportError:
        sys.stderr.write("Install the 'stripe' package first: pip install stripe\n")
        sys.exit(2)
    stripe.api_key = api_key
    return stripe


def _find_or_create_product(stripe: Any, *, code: str, name: str, description: str) -> str:
    """Look up product by metadata.code; create if missing. Returns product id."""
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if (p.get("metadata") or {}).get("code") == code:
            return p["id"]
    created = stripe.Product.create(
        name=name,
        description=description,
        metadata={"code": code},
    )
    return created["id"]


def _find_or_create_price(
    stripe: Any,
    *,
    product_id: str,
    unit_amount: int,
    currency: str = "usd",
    interval: str | None = None,
    lookup_key: str | None = None,
) -> str:
    """Find or create a Price. interval=None → one-time payment."""
    for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        ok_amount = int(price.get("unit_amount") or 0) == unit_amount
        ok_currency = (price.get("currency") or "").lower() == currency.lower()
        recurring = price.get("recurring") or {}
        ok_interval = (recurring.get("interval") if interval else None) == interval
        if ok_amount and ok_currency and ok_interval:
            return price["id"]
    kwargs: dict[str, Any] = {
        "product": product_id,
        "unit_amount": unit_amount,
        "currency": currency,
    }
    if interval:
        kwargs["recurring"] = {"interval": interval}
    if lookup_key:
        kwargs["lookup_key"] = lookup_key
    created = stripe.Price.create(**kwargs)
    return created["id"]


def main() -> int:
    api_key = os.environ.get("STRIPE_API_KEY", "")
    if not api_key or api_key.startswith("fake_"):
        sys.stderr.write(
            "STRIPE_API_KEY missing or 'fake_' — set a real test key first.\n"
        )
        return 1
    stripe = _get_stripe(api_key)

    print("[stripe_setup] connecting to Stripe…", file=sys.stderr)

    pro_product = _find_or_create_product(
        stripe,
        code="forexbot-pro",
        name="ForexBot Pro",
        description="Live trading + unlimited backtests + priority support.",
    )
    lifetime_product = _find_or_create_product(
        stripe,
        code="forexbot-lifetime",
        name="ForexBot Lifetime",
        description="One-time payment, lifetime Pro access.",
    )

    pro_monthly = _find_or_create_price(
        stripe,
        product_id=pro_product,
        unit_amount=2900,
        interval="month",
        lookup_key="forexbot_pro_monthly",
    )
    pro_yearly = _find_or_create_price(
        stripe,
        product_id=pro_product,
        unit_amount=29000,
        interval="year",
        lookup_key="forexbot_pro_yearly",
    )
    lifetime = _find_or_create_price(
        stripe,
        product_id=lifetime_product,
        unit_amount=99000,
        interval=None,
        lookup_key="forexbot_lifetime",
    )

    print("# --- Stripe Price IDs (paste into .env) ---")
    print(f"STRIPE_PRICE_PRO_MONTHLY={pro_monthly}")
    print(f"STRIPE_PRICE_PRO_YEARLY={pro_yearly}")
    print(f"STRIPE_PRICE_LIFETIME={lifetime}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
