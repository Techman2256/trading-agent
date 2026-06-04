from ai.ai_analyst import analyze_trade


def main() -> None:
    decision, confidence, reason = analyze_trade(
        "AAPL",
        "BUY",
        28.5,
        "ABOVE",
        189.42,
    )
    print("AI Analysis Test Result:")
    print(f"Decision: {decision}")
    print(f"Confidence: {confidence}")
    print(f"Reason: {reason}")


if __name__ == "__main__":
    main()
