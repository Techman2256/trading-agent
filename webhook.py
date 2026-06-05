from __future__ import annotations

import logging
import os
import requests
from flask import Flask, request, jsonify

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from data.market_data import fetch_multi_timeframe_data
from strategy.rsi_strategy import get_mtf_signal
from ai.ai_analyst import analyze_trade
from execution.order_executor import OrderExecutor
from execution.options_executor import OptionsExecutor
from risk.risk_manager import RiskManager
import threading

app = Flask(__name__)
logger = logging.getLogger("webhook")
logger.setLevel(logging.INFO)


def start_trading_bot() -> None:
    """Start the main trading loop in a background daemon thread."""

    def _run() -> None:
        try:
            from main import run_trading_loop

            logger.info("Starting trading bot in background thread")
            # Run trading loop (this will block inside the thread)
            run_trading_loop()
        except Exception as exc:
            logger.exception("Trading bot thread crashed: %s", exc)

    thread = threading.Thread(target=_run, daemon=True, name="trading-bot-thread")
    thread.start()
    logger.info("Trading bot thread started")


# Start trading bot when this module is imported/run so Railway (single process) runs both
start_trading_bot()


def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram credentials not set; unable to send message")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Failed to send Telegram message: %s", e)
        return False


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "invalid payload"}), 400

    symbol = data.get("symbol", "").upper()
    action = data.get("action", "").upper()
    price = float(data.get("price", 0))
    timeframe = data.get("timeframe", "1h")

    logger.info("TradingView signal received: %s %s @ $%.2f", action, symbol, price)

    try:
        data_mtf = fetch_multi_timeframe_data(symbol)
        mtf = get_mtf_signal(symbol, data_mtf.get("1h"), data_mtf.get("4h"), data_mtf.get("1d"))

        decision, confidence, reason = analyze_trade(
            symbol,
            action,
            mtf.tf_1h.rsi,
            mtf.tf_1h.ema_cross,
            mtf.tf_4h.rsi,
            mtf.tf_4h.ema_cross,
            mtf.tf_1d.rsi,
            mtf.tf_1d.ema_cross,
            mtf.support,
            mtf.resistance,
            price,
        )

        order_executor = OrderExecutor()
        options_executor = OptionsExecutor()
        risk_manager = RiskManager()

        if decision == "PROCEED" and confidence > 70:
            account = order_executor.get_account()
            qty = risk_manager.calculate_position_size(float(account.equity), price)

            if action == "BUY":
                if qty <= 0:
                    msg = f"⚠️ TRADINGVIEW SIGNAL: calculated qty is zero for {symbol}."
                    logger.warning(msg)
                    send_telegram_message(msg)
                else:
                    order = order_executor.place_market_order(symbol, qty, side="buy")
                    try:
                        options_executor.buy_call_option(symbol, price)
                    except Exception:
                        logger.warning("Failed to buy call option for %s", symbol)

                    msg = (
                        f"📊 TRADINGVIEW SIGNAL EXECUTED - {symbol} BUY @ ${price:.2f} | AI Confidence: {confidence}%"
                    )
                    send_telegram_message(msg)

            elif action == "SELL":
                current_qty = order_executor.get_position_qty(symbol)
                if current_qty <= 0:
                    msg = f"⚠️ TRADINGVIEW SIGNAL: no long position to sell for {symbol}."
                    logger.warning(msg)
                    send_telegram_message(msg)
                else:
                    order = order_executor.place_market_order(symbol, current_qty, side="sell")
                    try:
                        options_executor.buy_put_option(symbol, price)
                    except Exception:
                        logger.warning("Failed to buy put option for %s", symbol)

                    msg = (
                        f"📊 TRADINGVIEW SIGNAL EXECUTED - {symbol} SELL @ ${price:.2f} | AI Confidence: {confidence}%"
                    )
                    send_telegram_message(msg)

            else:
                msg = f"⚠️ TRADINGVIEW SIGNAL: unsupported action {action} for {symbol}."
                logger.warning(msg)
                send_telegram_message(msg)

        else:
            msg = f"⚠️ TRADINGVIEW SIGNAL SKIPPED - {symbol} | Reason: {reason} | AI Confidence: {confidence}%"
            logger.info(msg)
            send_telegram_message(msg)

        return jsonify({"status": "ok"}), 200

    except Exception as exc:
        logger.exception("Error processing TradingView webhook: %s", exc)
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    # Use PORT env var (required by Railway); default to 8080 for local testing
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
