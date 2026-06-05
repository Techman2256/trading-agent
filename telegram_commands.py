from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Coroutine

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from data.market_data import fetch_live_price, fetch_multi_timeframe_data
from execution.order_executor import OrderExecutor
from execution.options_executor import OptionsExecutor
from risk.risk_manager import RiskManager
from strategy.rsi_strategy import get_mtf_signal
from ai.ai_analyst import analyze_trade
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

logger = logging.getLogger("telegram_commands")
logger.setLevel(logging.INFO)

order_executor = OrderExecutor()
options_executor = OptionsExecutor()
risk_manager = RiskManager()

pending_actions: dict[int, dict[str, Any]] = {}


@dataclass
class PendingAction:
    action_type: str
    symbol: str
    shares: int | None = None
    option_type: str | None = None
    contract_symbol: str | None = None
    strike: float | None = None
    expiry: str | None = None
    price: float | None = None


def _normalize_chat_id(chat_id: int | str | None) -> str | None:
    if chat_id is None:
        return None
    try:
        return str(int(str(chat_id).strip()))
    except (ValueError, TypeError):
        normalized = str(chat_id).strip()
        return normalized if normalized else None


def _authorized(chat_id: int | None) -> bool:
    normalized_env_id = _normalize_chat_id(TELEGRAM_CHAT_ID)
    normalized_chat_id = _normalize_chat_id(chat_id)
    if not normalized_env_id or not normalized_chat_id:
        return False
    return normalized_env_id == normalized_chat_id


async def _reply(update: Update, text: str) -> None:
    try:
        if update.effective_chat:
            await update.effective_chat.send_message(text)
        elif update.message:
            await update.message.reply_text(text)
        else:
            logger.warning("Unable to reply: no chat or message available on update %s", update)
    except Exception as exc:
        logger.exception("Failed to send Telegram reply: %s", exc)


async def _not_authorized(update: Update) -> None:
    logger.warning("Unauthorized Telegram access attempt from chat_id=%s", update.effective_chat.id if update.effective_chat else None)
    await _reply(update, "Unauthorized chat. This bot only responds to the configured Telegram chat ID.")


async def _handle_telegram_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Telegram handler error for update %s: %s", update, context.error if hasattr(context, "error") else None)


CommandHandlerFunc = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


def _with_command_error_logging(handler: CommandHandlerFunc) -> CommandHandlerFunc:
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await handler(update, context)
        except Exception as exc:
            logger.exception("Telegram command /%s failed", handler.__name__)
            if update and update.effective_chat:
                try:
                    await _reply(update, f"Sorry, /{handler.__name__} failed: {exc}")
                except Exception:
                    logger.exception("Failed to send fallback error reply for /%s", handler.__name__)
    return wrapper


@_with_command_error_logging
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    msg = (
        "/buy SYMBOL SHARES - buys X shares of a stock\n"
        "/sell SYMBOL - sells all shares of a stock you own\n"
        "/short SYMBOL - shorts a stock using 2% position sizing\n"
        "/cover SYMBOL - covers a short position\n"
        "/call SYMBOL - buys 1 call option on a stock\n"
        "/put SYMBOL - buys 1 put option on a stock\n"
        "/positions - returns all current open positions\n"
        "/pnl - returns today's P&L and portfolio value\n"
        "/status - returns bot status, account equity, number of positions\n"
        "/confirm - execute the previously requested trade override\n"
        "/help - lists all available commands"
    )
    await _reply(update, msg)


@_with_command_error_logging
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    account = order_executor.get_account()
    positions = order_executor.list_positions()
    msg = (
        f"Bot status: ONLINE\n"
        f"Account equity: ${float(account.equity):.2f}\n"
        f"Positions: {len(positions)}"
    )
    await _reply(update, msg)


@_with_command_error_logging
async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    positions = order_executor.list_positions()
    if not positions:
        return await _reply(update, "No open positions.")

    lines: list[str] = []
    for pos in positions:
        lines.append(
            f"{pos.symbol}: {pos.qty} shares | Market value: ${float(pos.market_value):.2f} | P&L: ${float(pos.unrealized_pl):.2f}"
        )
    await _reply(update, "\n".join(lines))


@_with_command_error_logging
async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    account = order_executor.get_account()
    equity = float(account.equity)
    last_equity = float(account.last_equity)
    pnl_value = equity - last_equity
    msg = (
        f"Today's P&L: ${pnl_value:.2f}\n"
        f"Portfolio value: ${equity:.2f}"
    )
    await _reply(update, msg)


async def _run_ai_analysis(symbol: str, signal: str, price: float) -> tuple[str, int, str]:
    data = fetch_multi_timeframe_data(symbol)
    mtf = get_mtf_signal(symbol, data["1h"], data["4h"], data["1d"])
    return analyze_trade(
        symbol,
        signal,
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


@_with_command_error_logging
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    if len(context.args) < 2:
        return await _reply(update, "Usage: /buy SYMBOL SHARES")

    symbol = context.args[0].upper()
    try:
        shares = int(context.args[1])
    except ValueError:
        return await _reply(update, "Shares must be an integer.")

    price = fetch_live_price(symbol)
    decision, confidence, reason = await _run_ai_analysis(symbol, "STRONG BUY", price)

    if decision != "PROCEED" or confidence <= 70:
        pending_actions[update.effective_chat.id] = PendingAction(
            action_type="buy",
            symbol=symbol,
            shares=shares,
            price=price,
        ).__dict__
        await _reply(
            update,
            f"AI recommends SKIP for /buy {symbol} {shares}. Confidence: {confidence}%\n"
            f"Reason: {reason}\nReply /confirm to override AI and execute anyway.",
        )
        return

    order = order_executor.place_market_order(symbol, shares, side="buy")
    await _reply(update, f"BUY EXECUTED - {symbol} {shares} shares at order {order.id}")


@_with_command_error_logging
async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    if len(context.args) < 1:
        return await _reply(update, "Usage: /sell SYMBOL")

    symbol = context.args[0].upper()
    qty = order_executor.get_position_qty(symbol)
    if qty <= 0:
        return await _reply(update, f"No long position held for {symbol}.")

    order = order_executor.place_market_order(symbol, qty, side="sell")
    await _reply(update, f"SELL EXECUTED - {symbol} {qty} shares at order {order.id}")


@_with_command_error_logging
async def short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    if len(context.args) < 1:
        return await _reply(update, "Usage: /short SYMBOL")

    symbol = context.args[0].upper()
    price = fetch_live_price(symbol)
    account = order_executor.get_account()
    qty = risk_manager.calculate_position_size(float(account.equity), price)
    if qty <= 0:
        return await _reply(update, f"Calculated short quantity for {symbol} is zero.")

    decision, confidence, reason = await _run_ai_analysis(symbol, "SHORT", price)
    if decision != "PROCEED" or confidence <= 70:
        pending_actions[update.effective_chat.id] = PendingAction(
            action_type="short",
            symbol=symbol,
            shares=qty,
            price=price,
        ).__dict__
        await _reply(
            update,
            f"AI recommends SKIP for /short {symbol}. Confidence: {confidence}%\n"
            f"Reason: {reason}\nReply /confirm to override AI and execute anyway.",
        )
        return

    order = order_executor.place_short_market_order(symbol, qty)
    await _reply(update, f"SHORT EXECUTED - {symbol} {qty} shares at order {order.id}")


@_with_command_error_logging
async def cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    if len(context.args) < 1:
        return await _reply(update, "Usage: /cover SYMBOL")

    symbol = context.args[0].upper()
    qty = order_executor.get_position_qty(symbol)
    if qty >= 0:
        return await _reply(update, f"No short position held for {symbol}.")

    order = order_executor.place_market_order(symbol, abs(qty), side="buy")
    await _reply(update, f"COVER EXECUTED - {symbol} {abs(qty)} shares at order {order.id}")


async def _preview_option(
    update: Update,
    option_type: str,
    symbol: str,
) -> None:
    if not _authorized(update.effective_chat.id):
        return await _not_authorized(update)

    price = fetch_live_price(symbol)
    expiry = options_executor._get_target_expiry()
    try:
        contract = options_executor._select_contract(symbol, option_type, expiry)
    except Exception as exc:
        return await _reply(update, f"Unable to find {option_type} option contract for {symbol}: {exc}")

    strike = float(contract.get("strike_price", contract.get("strike", 0)))
    option_symbol = contract.get("symbol") or contract.get("option_symbol")
    pending_actions[update.effective_chat.id] = PendingAction(
        action_type=option_type,
        symbol=symbol,
        option_type=option_type,
        contract_symbol=option_symbol,
        strike=strike,
        expiry=contract.get("expiry_date") or contract.get("expiry"),
        price=price,
    ).__dict__

    await _reply(
        update,
        f"{option_type.upper()} PREVIEW - {symbol} ${strike:.0f} strike exp {expiry}\n"
        f"Underlying price: ${price:.2f}\n"
        f"Reply /confirm to execute this options trade.",
    )


@_with_command_error_logging
async def call_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        return await _reply(update, "Usage: /call SYMBOL")
    await _preview_option(update, "call", context.args[0].upper())


@_with_command_error_logging
async def put_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        return await _reply(update, "Usage: /put SYMBOL")
    await _preview_option(update, "put", context.args[0].upper())


@_with_command_error_logging
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update.effective_chat.id if update.effective_chat else None):
        return await _not_authorized(update)

    pending = pending_actions.get(update.effective_chat.id)
    if not pending:
        return await _reply(update, "No pending trade to confirm.")

    action = PendingAction(**pending)
    symbol = action.symbol.upper()
    try:
        if action.action_type == "buy" and action.shares:
            order = order_executor.place_market_order(symbol, action.shares, side="buy")
            await _reply(update, f"BUY EXECUTED - {symbol} {action.shares} shares at order {order.id}")
        elif action.action_type == "short" and action.shares:
            order = order_executor.place_short_market_order(symbol, action.shares)
            await _reply(update, f"SHORT EXECUTED - {symbol} {action.shares} shares at order {order.id}")
        elif action.action_type == "call":
            order_result = options_executor.buy_call_option(symbol, action.price or fetch_live_price(symbol))
            order_id = order_result["order"].get("id")
            await _reply(update, f"CALL OPTION EXECUTED - {symbol} strike ${action.strike:.0f} exp {action.expiry} order {order_id}")
        elif action.action_type == "put":
            order_result = options_executor.buy_put_option(symbol, action.price or fetch_live_price(symbol))
            order_id = order_result["order"].get("id")
            await _reply(update, f"PUT OPTION EXECUTED - {symbol} strike ${action.strike:.0f} exp {action.expiry} order {order_id}")
        else:
            await _reply(update, "Unknown pending action.")
            return
    except Exception as exc:
        await _reply(update, f"Failed to execute confirmed trade: {exc}")
        return
    finally:
        pending_actions.pop(update.effective_chat.id, None)


def _build_telegram_app() -> Application:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("pnl", pnl))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("short", short))
    app.add_handler(CommandHandler("cover", cover))
    app.add_handler(CommandHandler("call", call_option))
    app.add_handler(CommandHandler("put", put_option))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_error_handler(_handle_telegram_error)
    return app


def run_telegram_command_listener() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials missing; command listener will not start.")
        return

    while True:
        try:
            app = _build_telegram_app()
            logger.info("Starting Telegram command listener...")
            app.run_polling(stop_signals=None)
        except Exception as exc:
            logger.exception("Telegram command listener crashed unexpectedly: %s", exc)
            time.sleep(5)
