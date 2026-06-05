from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as dt_time, date
from pathlib import Path
from zoneinfo import ZoneInfo

from config import validate_config, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from data.market_data import SYMBOLS, fetch_live_price, fetch_multi_timeframe_data
from execution.order_executor import OrderExecutor
from execution.options_executor import OptionsExecutor
from risk.risk_manager import RiskManager
from strategy.rsi_strategy import get_mtf_signal
from ai.ai_analyst import analyze_trade
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
    options_executor = OptionsExecutor()
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
    # track which symbols have already been sent an AI SKIP notification today
    skip_notif_day = date.today()
    skip_notified_symbols: set[str] = set()

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
        # reset daily skip notifications at midnight
        if date.today() != skip_notif_day:
            skip_notified_symbols.clear()
            skip_notif_day = date.today()

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
                    timeframe_data = fetch_multi_timeframe_data(symbol)
                    mtf_details = get_mtf_signal(
                        symbol,
                        timeframe_data["1h"],
                        timeframe_data["4h"],
                        timeframe_data["1d"],
                    )
                    signal = mtf_details.signal
                    logger.info(
                        "%s - 1H: RSI %.1f EMA %s | 4H: RSI %.1f EMA %s | 1D: RSI %.1f EMA %s | Support: $%.2f → %s",
                        symbol,
                        mtf_details.tf_1h.rsi if mtf_details.tf_1h.rsi is not None else 0.0,
                        mtf_details.tf_1h.ema_cross,
                        mtf_details.tf_4h.rsi if mtf_details.tf_4h.rsi is not None else 0.0,
                        mtf_details.tf_4h.ema_cross,
                        mtf_details.tf_1d.rsi if mtf_details.tf_1d.rsi is not None else 0.0,
                        mtf_details.tf_1d.ema_cross,
                        mtf_details.support if mtf_details.support is not None else 0.0,
                        signal,
                    )

                    current_qty = executor.get_position_qty(symbol)
                    # count current short positions across account
                    current_short_positions = executor.count_short_positions()

                    if signal == "HOLD":
                        continue

                    live_price = None
                    ai_decision = "SKIP"
                    ai_confidence = 0
                    ai_reason = "No AI analysis available"
                    try:
                        if signal in {"STRONG BUY", "SHORT"}:
                            live_price = fetch_live_price(symbol)
                            ai_decision, ai_confidence, ai_reason = analyze_trade(
                                symbol,
                                signal,
                                mtf_details.tf_1h.rsi,
                                mtf_details.tf_1h.ema_cross,
                                mtf_details.tf_4h.rsi,
                                mtf_details.tf_4h.ema_cross,
                                mtf_details.tf_1d.rsi,
                                mtf_details.tf_1d.ema_cross,
                                mtf_details.support,
                                mtf_details.resistance,
                                live_price,
                            )
                    except Exception as ai_err:
                        logger.warning("AI analysis failed for %s: %s", symbol, ai_err)

                    logger.info(
                        "AI Analysis: %s - Confidence: %d - %s",
                        ai_decision,
                        ai_confidence,
                        ai_reason,
                    )

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
                        if ai_decision != "PROCEED" or ai_confidence <= 70:
                            logger.info(
                                "Skipping buy for %s due to AI analysis: %s Confidence: %d Reason: %s",
                                symbol,
                                ai_decision,
                                ai_confidence,
                                ai_reason,
                            )
                            if telegram_enabled:
                                try:
                                    if symbol not in skip_notified_symbols:
                                        msg = (
                                            f"⚠️ BUY SKIPPED - {symbol}\n"
                                            f"RSI: {details.rsi if details.rsi is not None else 0.0:.1f} | AI Confidence: {ai_confidence}%\n"
                                            f"🧠 AI: {ai_reason}"
                                        )
                                        send_telegram_message(msg, logger=logger)
                                        skip_notified_symbols.add(symbol)
                                except Exception as e:
                                    logger.warning("Failed to send BUY SKIP Telegram message: %s", e)
                            continue
                        if live_price is None:
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
                        if telegram_enabled:
                            try:
                                msg = (
                                    f"🟢 BUY EXECUTED - {symbol}\n"
                                    f"Shares: {order_qty} | Price: ${live_price:.2f}\n"
                                    f"RSI: {details.rsi if details.rsi is not None else 0.0:.1f} | AI Confidence: {ai_confidence}%\n"
                                    f"🧠 AI Reasoning: {ai_reason}"
                                )
                                send_telegram_message(msg, logger=logger)
                            except Exception as e:
                                logger.warning("Failed to send BUY Telegram message: %s", e)

                        try:
                            option_result = options_executor.buy_call_option(symbol, live_price)
                            contract = option_result["contract"]
                            strike = float(contract.get("strike_price", contract.get("strike", 0)))
                            expiry = contract.get("expiry_date") or contract.get("expiry")
                            logger.info(
                                "CALL OPTION BOUGHT - %s $%.0f strike exp %s",
                                symbol,
                                strike,
                                expiry,
                            )
                            if telegram_enabled:
                                msg = (
                                    f"📈 CALL OPTION - {symbol} ${strike:.0f} strike | AI Confidence: {ai_confidence}%"
                                )
                                send_telegram_message(msg, logger=logger)
                        except Exception as e:
                            logger.warning("Failed to buy call option for %s: %s", symbol, e)

                    elif signal == "SHORT":
                        if current_qty < 0:
                            logger.info("Already short %s shares of %s", abs(current_qty), symbol)
                            continue
                        if not risk_manager.can_open_short_position(current_short_positions):
                            logger.warning("Skipping short for %s due to short position limits", symbol)
                            continue
                        if ai_decision != "PROCEED" or ai_confidence <= 70:
                            logger.info(
                                "Skipping short for %s due to AI analysis: %s Confidence: %d Reason: %s",
                                symbol,
                                ai_decision,
                                ai_confidence,
                                ai_reason,
                            )
                            if telegram_enabled:
                                try:
                                    if symbol not in skip_notified_symbols:
                                        msg = (
                                            f"⚠️ SHORT SKIPPED - {symbol}\n"
                                            f"RSI: {details.rsi if details.rsi is not None else 0.0:.1f} | AI Confidence: {ai_confidence}%\n"
                                            f"🧠 AI: {ai_reason}"
                                        )
                                        send_telegram_message(msg, logger=logger)
                                        skip_notified_symbols.add(symbol)
                                except Exception as e:
                                    logger.warning("Failed to send SHORT SKIP Telegram message: %s", e)
                            continue
                        if live_price is None:
                            live_price = fetch_live_price(symbol)
                        try:
                            option_result = options_executor.buy_put_option(symbol, live_price)
                            contract = option_result["contract"]
                            strike = float(contract.get("strike_price", contract.get("strike", 0)))
                            expiry = contract.get("expiry_date") or contract.get("expiry")
                            logger.info(
                                "PUT OPTION BOUGHT - %s $%.0f strike exp %s",
                                symbol,
                                strike,
                                expiry,
                            )
                            if telegram_enabled:
                                msg = (
                                    f"📉 PUT OPTION - {symbol} ${strike:.0f} strike | AI Confidence: {ai_confidence}%"
                                )
                                send_telegram_message(msg, logger=logger)
                        except Exception as e:
                            logger.warning("Failed to buy put option for %s: %s", symbol, e)

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
                        # SELL executed notifications are intentionally not sent to Telegram
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
