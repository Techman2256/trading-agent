from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from config import validate_config, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from data.market_data import SYMBOLS, fetch_historical_data, fetch_live_price
from execution.order_executor import OrderExecutor
from risk.risk_manager import RiskManager
from strategy.rsi_strategy import get_signal_details
import requests

LOG_PATH = Path("logs") / "trades.log"
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)
SLEEP_SECONDS = 300


def setup_logger() -> logging.Logger:
    """Configure logging to file and standard output."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("trading_agent")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def is_market_open(current_time: datetime) -> bool:
    """Return True when the current time is within US market hours."""
    return (
        current_time.weekday() < 5
        and MARKET_OPEN <= current_time.time() < MARKET_CLOSE
    )


def is_market_close_warning_time(current_time: datetime) -> bool:
    """Return True when it is 3:55pm EST to 4:00pm EST on a weekday."""
    return (
        current_time.weekday() < 5
        and dt_time(15, 55) <= current_time.time() < MARKET_CLOSE
    )


def is_market_closed_for_day(current_time: datetime) -> bool:
    """Return True when the market has closed for the current weekday."""
    return current_time.weekday() < 5 and current_time.time() >= MARKET_CLOSE


def send_telegram_message(text: str, logger: logging.Logger | None = None) -> bool:
    """Send a Telegram message using the Telegram Bot API via HTTP POST."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        if logger:
            logger.info("Telegram credentials not set; unable to send message")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        if logger:
            logger.warning("Failed to send Telegram message: %s", e)
        return False


def run_trading_loop(test_close: bool = False) -> None:
    """Main trading loop that polls signals and places orders every 5 minutes."""
    validate_config()
    logger = setup_logger()
    executor = OrderExecutor()
    risk_manager = RiskManager()
    telegram_enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    if telegram_enabled:
        startup_msg = f"🤖 Trading Bot is now LIVE and watching {len(SYMBOLS)} stocks!"
        try:
            send_telegram_message(startup_msg, logger=logger)
        except Exception as e:
            logger.warning("Failed to send startup Telegram message: %s", e)
    else:
        logger.info("Telegram credentials not set; skipping Telegram notifications")

    logger.info("Starting trading loop")
    close_warning_sent = False

    if test_close:
        logger.info("Market close test mode active: simulating 3:55pm warning and 4:00pm shutdown.")
        warning_msg = "⚠️ Market closing in 5 minutes!"
        logger.info(warning_msg)
        if telegram_enabled:
            send_telegram_message(warning_msg, logger=logger)

        shutdown_msg = (
            "🔴 Market closed for the day. Bot is shutting down. "
            "Check Alpaca for today's positions."
        )
        logger.info("Market closed for the day. Bot shutting down.")
        if telegram_enabled:
            send_telegram_message(shutdown_msg, logger=logger)
        sys.exit(0)

    while True:
        current_time = datetime.now(MARKET_TZ)

        if is_market_closed_for_day(current_time):
            shutdown_msg = (
                "🔴 Market closed for the day. Bot is shutting down. "
                "Check Alpaca for today's positions."
            )
            logger.info("Market closed for the day. Bot shutting down.")
            if telegram_enabled:
                send_telegram_message(shutdown_msg, logger=logger)
            sys.exit(0)

        if is_market_close_warning_time(current_time) and not close_warning_sent:
            warning_msg = "⚠️ Market closing in 5 minutes!"
            logger.info(warning_msg)
            if telegram_enabled:
                send_telegram_message(warning_msg, logger=logger)
            close_warning_sent = True

        if not is_market_open(current_time):
            logger.info("Market is closed. Sleeping until next check.")
            time.sleep(SLEEP_SECONDS)
            continue

        try:
            account = executor.get_account()
            current_open_positions = len(executor.list_positions())
            daily_loss_pct = risk_manager.calculate_daily_loss_pct(
                float(account.equity), float(account.last_equity)
            )
            logger.info(
                "Account equity=%s open_positions=%d daily_loss_pct=%.2f%%",
                account.equity,
                current_open_positions,
                daily_loss_pct * 100,
            )

            for symbol in SYMBOLS:
                try:
                    historical = fetch_historical_data(symbol, period="60d", interval="1d")
                    details = get_signal_details(historical)
                    signal = details.signal
                    logger.info(
                        "%s %s - RSI: %.1f EMA cross: %s",
                        symbol,
                        signal,
                        details.rsi if details.rsi is not None else 0.0,
                        details.ema_cross,
                    )

                    current_qty = executor.get_position_qty(symbol)
                    # count current short positions across account
                    current_short_positions = executor.count_short_positions()

                    # Cover short positions when RSI dropped below threshold
                    if current_qty < 0 and risk_manager.should_cover_short(details.rsi):
                        pos = executor.get_position(symbol)
                        pl = 0.0
                        if pos is not None and hasattr(pos, "unrealized_pl"):
                            try:
                                pl = float(pos.unrealized_pl)
                            except Exception:
                                pl = 0.0
                        cover_qty = abs(current_qty)
                        order = executor.place_market_order(symbol, cover_qty, side="buy")
                        current_open_positions = max(current_open_positions - 1, 0)
                        logger.info(
                            "✅ SHORT COVERED - Stock: %s Profit/Loss: $%.2f",
                            symbol,
                            pl,
                        )
                        if telegram_enabled:
                            try:
                                msg = (
                                    f"✅ SHORT COVERED - Stock: {symbol} Profit/Loss: ${pl:.2f}"
                                )
                                send_telegram_message(msg, logger=logger)
                            except Exception as e:
                                logger.warning("Failed to send SHORT COVER Telegram message: %s", e)
                        # after covering, skip further processing this symbol this cycle
                        continue

                    if signal == "STRONG BUY":
                        if current_qty > 0:
                            logger.info("Already holding %s shares of %s", current_qty, symbol)
                            continue
                        if not risk_manager.can_open_position(
                            float(account.equity),
                            current_open_positions,
                            daily_loss_pct,
                        ):
                            logger.warning("Skipping buy for %s due to risk limits", symbol)
                            continue
                        live_price = fetch_live_price(symbol)
                        order_qty = risk_manager.calculate_position_size(
                            float(account.equity), live_price
                        )
                        if order_qty <= 0:
                            logger.warning(
                                "Calculated order quantity for %s is zero; skipping",
                                symbol,
                            )
                            continue
                        order = executor.place_market_order(symbol, order_qty, side="buy")
                        current_open_positions += 1
                        logger.info(
                            "Placed BUY order for %s qty=%d id=%s",
                            symbol,
                            order_qty,
                            order.id,
                        )
                        # Send Telegram notification for BUY
                        if telegram_enabled:
                            now = datetime.now(MARKET_TZ)

                    elif signal == "SHORT":
                        # open a new short position
                        if current_qty < 0:
                            logger.info("Already short %s shares of %s", abs(current_qty), symbol)
                            continue
                        if not risk_manager.can_open_short_position(current_short_positions):
                            logger.warning("Skipping short for %s due to short position limits", symbol)
                            continue
                        live_price = fetch_live_price(symbol)
                        # use explicit position sizing API (account_equity, price)
                        order_qty = risk_manager.calculate_position_size(
                            float(account.equity), live_price
                        )
                        if order_qty <= 0:
                            logger.warning(
                                "Calculated short order quantity for %s is zero; skipping",
                                symbol,
                            )
                            continue
                        order = executor.place_short_market_order(symbol, order_qty)
                        current_open_positions += 1
                        logger.info(
                            "Placed SHORT SELL order for %s qty=%d id=%s",
                            symbol,
                            order_qty,
                            order.id,
                        )
                        # Send Telegram notification for SHORT
                        if telegram_enabled:
                            try:
                                msg = (
                                    f"🔴 SHORT SELL - Stock: {symbol} RSI: {details.rsi:.1f}"
                                )
                                send_telegram_message(msg, logger=logger)
                            except Exception as e:
                                logger.warning("Failed to send SHORT Telegram message: %s", e)

                    elif signal == "STRONG SELL":
                        if current_qty <= 0:
                            logger.info(
                                "SELL signal for %s ignored because no position is held",
                                symbol,
                            )
                            continue
                        order = executor.place_market_order(symbol, current_qty, side="sell")
                        current_open_positions = max(current_open_positions - 1, 0)
                        logger.info(
                            "Placed SELL order for %s qty=%d id=%s",
                            symbol,
                            current_qty,
                            order.id,
                        )
                        # Send Telegram notification for SELL
                        if telegram_enabled:
                            try:
                                live_price = fetch_live_price(symbol)
                            except Exception:
                                live_price = None
                            now = datetime.now(MARKET_TZ)
                            time_str = now.strftime("%I:%M%p").lstrip("0").lower() + " EST"
                            price_text = f"Price: ${live_price:.2f}\n" if live_price is not None else ""
                            msg = (
                                f"🔴 SELL EXECUTED\n"
                                f"Stock: {symbol}\n"
                                f"Shares: {current_qty}\n"
                                f"{price_text}"
                                f"Time: {time_str}"
                            )
                            try:
                                send_telegram_message(msg, logger=logger)
                            except Exception as e:
                                logger.warning("Failed to send SELL Telegram message: %s", e)
                except Exception as symbol_error:
                    logger.error("Error processing %s: %s", symbol, symbol_error)
        except Exception as err:
            logger.error("Unexpected trading loop error: %s", err)

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the trading bot or simulate market close notifications.")
    parser.add_argument(
        "--test-close",
        action="store_true",
        help="Run a market close simulation: 3:55pm warning and 4:00pm shutdown.",
    )
    args = parser.parse_args()
    run_trading_loop(test_close=args.test_close)
