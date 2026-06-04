from __future__ import annotations

import math
from typing import Optional

MAX_RISK_PER_TRADE = 0.02
MAX_OPEN_POSITIONS = 5
MAX_DAILY_LOSS = 0.03
MAX_SHORT_POSITIONS = 3


class RiskManager:
    """Apply risk-management rules before executing a trade."""

    def can_open_position(
        self,
        account_equity: float,
        current_open_positions: int,
        daily_loss_pct: float,
    ) -> bool:
        """Return True if a new trade may be opened under risk rules."""
        if daily_loss_pct <= -MAX_DAILY_LOSS:
            return False
        if current_open_positions >= MAX_OPEN_POSITIONS:
            return False
        return True

    def can_open_short_position(self, current_short_positions: int) -> bool:
        """Return True if a new short trade may be opened under short limits."""
        if current_short_positions >= MAX_SHORT_POSITIONS:
            return False
        return True

    def calculate_trade_quantity(
        self,
        symbol_price: float,
        account_equity: float,
    ) -> int:
        """Calculate maximum shares for a single trade while limiting risk to 2% of equity."""
        if symbol_price <= 0:
            return 0
        max_risk_dollars = account_equity * MAX_RISK_PER_TRADE
        quantity = math.floor(max_risk_dollars / symbol_price)
        return max(quantity, 0)

    def calculate_position_size(self, account_equity: float, symbol_price: float) -> int:
        """Return integer number of shares sized so that risk <= 2% of account equity.

        This method explicitly takes `account_equity` first then `symbol_price` to
        avoid confusion and is intended for both long and short sizing.
        """
        if symbol_price <= 0:
            return 0
        max_risk_dollars = account_equity * MAX_RISK_PER_TRADE
        qty = math.floor(max_risk_dollars / symbol_price)
        return max(int(qty), 0)

    def calculate_daily_loss_pct(
        self,
        current_equity: float,
        previous_equity: float,
    ) -> float:
        """Compute the percentage daily loss relative to previous equity."""
        if previous_equity <= 0:
            return 0.0
        return (current_equity - previous_equity) / previous_equity

    def should_close_position(self, signal: str) -> bool:
        """Return True when the current signal indicates a position should be closed."""
        return signal == "SELL"

    def should_cover_short(self, current_rsi: Optional[float]) -> bool:
        """Return True when a short should be covered (RSI dropped below threshold)."""
        if current_rsi is None:
            return False
        return current_rsi < 45
