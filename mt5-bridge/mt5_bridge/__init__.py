"""MT5 bridge — Windows-side service that exposes the `MetaTrader5`
Python package over HTTP so the Linux/Mac backend can place orders.

Architecture
------------
    [trading-engine on Linux] --HTTPS+Bearer--> [mt5-bridge on Windows] --IPC--> [MT5 Terminal] --> [Exness]

The bridge is intentionally a *thin shim*. All policy (strategy logic,
risk checks, slippage modeling) lives in the trading-engine. The bridge
adds one belt-and-braces safety layer (`safety.py`) — never trust the
caller blindly.
"""
__version__ = "0.1.0"
