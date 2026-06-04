"""Export dry run JSONL results to CSV, enriching with price and live price.

Usage: run from repo root with PYTHONPATH=. to allow local imports.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from data.market_data import fetch_historical_data, fetch_live_price


def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    sym = entry.get("symbol")
    price = None
    live_price = None
    try:
        hist = fetch_historical_data(sym, period="7d", interval="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
    except Exception:
        price = None
    try:
        live_price = float(fetch_live_price(sym))
    except Exception:
        live_price = None

    entry["price"] = price
    entry["live_price"] = live_price
    return entry


def export(jsonl_path: str = "logs/dry_run_results.jsonl", csv_path: str = "logs/dry_run_results.csv") -> None:
    jsonl = Path(jsonl_path)
    if not jsonl.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl}")

    rows: list[dict[str, Any]] = []
    with jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            rows.append(enrich_entry(entry))

    if not rows:
        print("No rows to export.")
        return

    # determine fieldnames
    fieldnames = [
        "timestamp",
        "symbol",
        "signal",
        "rsi",
        "ema_cross",
        "qty",
        "action",
        "pl",
        "price",
        "live_price",
        "order_id",
        "order_qty",
    ]
    outp = Path(csv_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            # ensure all fields exist
            out = {k: r.get(k) for k in fieldnames}
            writer.writerow(out)

    print(f"Exported {len(rows)} rows to {csv_path}")


if __name__ == "__main__":
    export()
