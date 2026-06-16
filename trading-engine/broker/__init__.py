"""Broker adapters: MT5 (Exness) + paper for backtest/staging."""

from broker.base import Broker, Order, OrderResult, Position
from broker.paper_adapter import PaperBroker

__all__ = ["Broker", "Order", "OrderResult", "Position", "PaperBroker"]
