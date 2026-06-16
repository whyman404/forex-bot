"""Live-trading subsystem.

Glues together:
    - strategies/  (signal generation)
    - risk/        (gatekeeper)
    - mt5-bridge   (Windows-side broker proxy)
    - backend      (signal + trade + heartbeat ingestion)

Module map
----------
    engine.py          — LiveEngine, one per running strategy instance
    router.py          — picks the right engine/broker for a strategy
    circuit_breaker.py — daily loss, max DD, disconnect, slippage breakers
    internal_client.py — HMAC-signed POSTs to backend /internal/*
    gate.py            — Paper -> Live promotion gate (mirrors Atlas's checks)
    monitor.py         — per-engine health/PnL endpoint for Atlas
    server_endpoints.py — adds /live/* routes to server.py
"""
