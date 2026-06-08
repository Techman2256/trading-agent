import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from .news_analyst import get_news_sentiment

# Load ANTHROPIC_API_KEY from the repository .env file if present.
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY must be set in the .env file")

client = anthropic.Client(api_key=ANTHROPIC_API_KEY)


def analyze_trade(
    symbol: str,
    signal: str,
    rsi_1h: float | None,
    ema_1h: str,
    rsi_4h: float | None,
    ema_4h: str,
    rsi_1d: float | None,
    ema_1d: str,
    support: float | None,
    resistance: float | None,
    price: float,
) -> tuple[str, int, str, str, int, str]:
    """Ask Claude to analyze whether to proceed with a proposed trade."""
    if rsi_1h is None or rsi_4h is None or rsi_1d is None:
        raise ValueError("All timeframe RSI values must be provided for AI trade analysis")

    support_text = f"${support:.2f}" if support is not None else "N/A"
    resistance_text = f"${resistance:.2f}" if resistance is not None else "N/A"

    # Get recent news sentiment first and include it in the analysis prompt
    news_sentiment, news_confidence, news_summary = get_news_sentiment(symbol)

    prompt = (
        f"{anthropic.HUMAN_PROMPT}You are an experienced trading analyst. "
        f"Evaluate the trade below and decide whether to PROCEED or SKIP. "
        f"Keep your response in the following format:\n"
        f"DECISION: PROCEED or SKIP\n"
        f"CONFIDENCE: 1-100\n"
        f"REASON: <brief reason>\n\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"1H RSI: {rsi_1h:.2f} | EMA: {ema_1h}\n"
        f"4H RSI: {rsi_4h:.2f} | EMA: {ema_4h}\n"
        f"1D RSI: {rsi_1d:.2f} | EMA: {ema_1d}\n"
        f"Support: {support_text}\n"
        f"Resistance: {resistance_text}\n"
        f"Price: ${price:.2f}\n"
        f"News Sentiment: {news_sentiment} (Confidence: {news_confidence}%)\n"
        f"Latest: {news_summary}\n"
        f"Consider the news sentiment when making your decision.{anthropic.AI_PROMPT}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    text = response.content[0].text if response and response.content else ""

    decision = "SKIP"
    confidence = 0
    reason = text.strip()

    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if key == "DECISION":
            if value.upper() in {"PROCEED", "SKIP"}:
                decision = value.upper()
        elif key == "CONFIDENCE":
            try:
                confidence = int(value)
            except ValueError:
                confidence = 0
        elif key == "REASON":
            reason = value

    # Factor news sentiment into the final confidence
    try:
        if news_sentiment == "BULLISH":
            confidence = min(100, confidence + 10)
        elif news_sentiment == "BEARISH":
            confidence = max(0, confidence - 10)
    except Exception:
        pass

    return decision, confidence, reason, news_sentiment, news_confidence, news_summary


def test_anthropic_connection() -> None:
    """Run a quick Claude trade analysis test to verify Anthropic connectivity."""
    decision, confidence, reason = analyze_trade(
        "AAPL",
        "STRONG BUY",
        28.5,
        "ABOVE",
        30.0,
        "ABOVE",
        42.0,
        "ABOVE",
        195.0,
        210.0,
        189.42,
    )
    print("AI Analysis Test Result:")
    print(f"Decision: {decision}")
    print(f"Confidence: {confidence}")
    print(f"Reason: {reason}")


if __name__ == "__main__":
    test_anthropic_connection()
