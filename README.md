# Trading Agent

This repository contains an agentic trading bot project structure for algorithmic trading.

## Overview

- `data/`: data ingestion and market data utilities
- `strategy/`: strategy definitions and trading signals
- `risk/`: risk management and position sizing
- `execution/`: order execution and broker integration
- `logs/`: trading logs and audit files
- `tests/`: unit tests and validation code

## Setup

1. Copy `.env.template` to `.env`.
2. Fill in your `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ANTHROPIC_API_KEY`.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Notes

This project is structured for a modular algorithmic trading agent. Each folder is intended to isolate responsibilities for data, strategy, risk control, and execution.
