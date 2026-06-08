import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Load ANTHROPIC_API_KEY from the repository .env file if present.
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY must be set in the .env file")

client = anthropic.Client(api_key=ANTHROPIC_API_KEY)


def _parse_response(text: str) -> tuple[str, int, str]:
    sentiment = "NEUTRAL"
    confidence = 0
    summary = text.strip()

    for line in text.splitlines():
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if key in {"SENTIMENT", "NEWS SENTIMENT"}:
            sentiment = value.upper()
        elif key == "CONFIDENCE":
            try:
                confidence = int(value)
            except Exception:
                confidence = 0
        elif key == "SUMMARY":
            summary = value

    return sentiment, confidence, summary


def get_news_sentiment(symbol: str) -> tuple[str, int, str]:
    """Ask Claude to search recent news for `symbol` and return sentiment.

    Returns: (sentiment, confidence 1-100, brief summary)
    """
    prompt = (
        f"{anthropic.HUMAN_PROMPT}You are a financial news researcher. "
        f"Search for recent news (last 48 hours) about the stock symbol {symbol} and evaluate whether the overall news tone is BULLISH, BEARISH, or NEUTRAL. "
        f"Respond strictly in the following format:\n"
        f"SENTIMENT: BULLISH|BEARISH|NEUTRAL\n"
        f"CONFIDENCE: 1-100\n"
        f"SUMMARY: <one-line summary of the most important recent headline or development>\n"
        f"If no recent news is found, respond with SENTIMENT: NEUTRAL and an appropriate SUMMARY.\n"
        f"{anthropic.AI_PROMPT}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text if response and response.content else ""
    sentiment, confidence, summary = _parse_response(text)
    # sanitize
    if sentiment not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        sentiment = "NEUTRAL"
    confidence = max(0, min(100, int(confidence) if isinstance(confidence, int) else 0))
    summary = summary.strip()
    return sentiment, confidence, summary
