"""Strategy implementations.

Each strategy subclasses `Strategy` from `strategies.base` and implements
`prepare()` and `signals()`.
"""

from strategies.base import Strategy, SignalRow

__all__ = ["Strategy", "SignalRow"]
