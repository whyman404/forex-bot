-- Seed the 6 catalog strategies. Idempotent via ON CONFLICT (code).
-- Owned by Mnemosyne (schema) — Atlas keeps this script in sync with API tests.

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
     '{"levels": 10, "step_pct": 0.5}'::jsonb)
ON CONFLICT (code) DO UPDATE
    SET display_name   = EXCLUDED.display_name,
        description    = EXCLUDED.description,
        asset_class    = EXCLUDED.asset_class,
        risk_rating    = EXCLUDED.risk_rating,
        default_params = EXCLUDED.default_params,
        updated_at     = now();
