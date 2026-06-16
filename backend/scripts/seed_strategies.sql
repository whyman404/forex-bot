-- Seed the catalog strategies. Idempotent via ON CONFLICT (code).
-- Owned by Mnemosyne (schema) — Atlas keeps this script in sync with API tests.
--
-- 2026-06-16 — added `tv_signal` (round 4). Requires migration 0005 to have
-- relaxed `strategies_code_check` + `strategies_asset_class_check`. If you
-- run this against a DB at revision 0002–0004, the INSERT for tv_signal
-- will fail the CHECK. Run `alembic upgrade head` first.

\set ON_ERROR_STOP on

INSERT INTO strategies (code, display_name, asset_class, risk_rating, description, default_params)
VALUES
    ('london_breakout', 'London Breakout',  'gold', 'medium',
     'Breakout above/below London session range.',
     '{"session_open": "07:00", "session_close": "10:00", "atr_period": 14}'::jsonb),
    ('ny_killzone',    'New York Killzone', 'gold', 'medium',
     'NY session momentum capture.',
     '{"session_open": "12:30", "session_close": "15:00", "rr": 2.0}'::jsonb),
    ('ema_adx',        'EMA + ADX Trend',   'gold', 'low',
     'Trend follower with ADX filter.',
     '{"ema_fast": 21, "ema_slow": 55, "adx_min": 20}'::jsonb),
    ('ema_rsi',        'EMA + RSI Pullback','btc',  'medium',
     'Trend pullbacks via RSI on BTC.',
     '{"ema": 50, "rsi_period": 14, "rsi_lo": 35, "rsi_hi": 65}'::jsonb),
    ('donchian',       'Donchian Channel',  'btc',  'high',
     'Classic Donchian breakout.',
     '{"channel": 20, "trail": 10}'::jsonb),
    ('grid',           'Grid Range',        'btc',  'high',
     'Grid in ranging markets — high risk.',
     '{"levels": 10, "step_pct": 0.5}'::jsonb),
    ('tv_signal',      'TradingView Signal Follow', 'multi', 'medium',
     'Multi-timeframe TradingView recommendation following with ATR-based risk management.',
     '{
        "symbols": [],
        "intervals": ["1h", "4h", "1d"],
        "long_threshold": 0.5,
        "short_threshold": -0.5,
        "atr_period": 14,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 3.0,
        "cool_down_min": 60,
        "risk_per_trade_pct": 1.0,
        "max_trades_per_day": 6,
        "spread_filter_pts": 30,
        "enabled": true
     }'::jsonb)
ON CONFLICT (code) DO UPDATE
    SET display_name   = EXCLUDED.display_name,
        description    = EXCLUDED.description,
        asset_class    = EXCLUDED.asset_class,
        risk_rating    = EXCLUDED.risk_rating,
        default_params = EXCLUDED.default_params,
        updated_at     = now();

-- requires_external_service is added by migration 0005; populate it here
-- so dev seeds match migration semantics. The UPDATE is a no-op when the
-- column doesn't yet exist (we guard via DO block).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'strategies'
           AND column_name = 'requires_external_service'
    ) THEN
        UPDATE strategies
           SET requires_external_service = TRUE
         WHERE code = 'tv_signal';
        UPDATE strategies
           SET requires_external_service = FALSE
         WHERE code <> 'tv_signal'
           AND requires_external_service IS DISTINCT FROM FALSE;
    END IF;
END$$;
