import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from a .env file if present
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def validate_config() -> None:
    """Raise an error if required Alpaca environment variables are missing."""
    missing = [
        key for key in [
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "ALPACA_BASE_URL",
            "ANTHROPIC_API_KEY",
        ]
        if not os.getenv(key)
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
