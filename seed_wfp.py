"""
seed_wfp.py — Seeds WFP Nigeria food price data into PriceWise DB
Adds products, price_history, and state_prices from real UN data.
Only uses 2022+ prices (most relevant/recent).
Run once — skips if already seeded.
"""

import csv
import sqlite3
import os
from collections import defaultdict
from datetime import date

DB_PATH = os.environ.get("DB_PATH", "pricewise.db")
CSV_PATH = os.environ.get("WFP_CSV", "wfp_food_prices_nga.csv")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def already_seeded(conn):
    count = conn.execute(
        "SELECT COUNT(*) FROM products WHERE name LIKE '%Maize%' OR name LIKE '%Garri%' OR name LIKE '%Yam%'"
    ).fetchone()[0]
    return count > 0


def load_wfp_data(csv_path, min_date="2022-01-01"):
    """Load WFP CSV, return latest price per commodity+state (2022+)."""
    latest = {}

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        next(reader)  # skip WFP metadata row

        for row in reader:
            if not row["price"] or not row["date"]:
                continue
            if row["date"] < min_date:
                continue

            try:
                price = float(row["price"])
            except ValueError:
                continue

            if price <= 0:
                continue

            commodity = row["commodity"].strip()
            state = row["admin1"].strip()
            key = (commodity, state)

            if key not in latest or row["date"] > latest[key]["date"]:
                latest[key] = {
                    "commodity": commodity,
                    "state": state,
                    "market": row["market"].strip(),
                    "price": price,
                    "unit": row["unit"].strip(),
                    "pricetype": row["pricetype"].strip(),
                    "date": row["date"][:10],
                    "category": row["category"].strip()
                }

    return list(latest.values())


def seed(csv_path=CSV_PATH):
    conn = get_db()

    if already_seeded(conn):
        print("[wfp] Already seeded, skipping.")
        conn.close()
        return

    print(f"[wfp] Loading from {csv_path}...")
    records = load_wfp_data(csv_path)
    print(f"[wfp] {len(records)} records loaded.")

    c = conn.cursor()

    # Group records by commodity
    by_commodity = defaultdict(list)
    for r in records:
        by_commodity[r["commodity"]].append(r)

    products_added = 0
    prices_added = 0
    state_prices_added = 0

    for commodity, entries in by_commodity.items():
        # Get or create product
        c.execute("SELECT id FROM products WHERE name = ?", (commodity,))
        row = c.fetchone()

        if row:
            product_id = row["id"]
        else:
            c.execute(
                "INSERT INTO products (name, url) VALUES (?, ?)",
                (commodity, "")
            )
            product_id = c.lastrowid
            products_added += 1

        # Add price_history entries (one per state)
        for entry in entries:
            c.execute("""
                INSERT INTO price_history (product_id, price, platform, date)
                VALUES (?, ?, ?, ?)
            """, (
                product_id,
                entry["price"],
                entry["pricetype"],
                entry["date"]
            ))
            prices_added += 1

            # Add state_prices
            c.execute("""
                INSERT OR IGNORE INTO state_prices
                (product_id, state, price, platform, date, source)
                VALUES (?, ?, ?, ?, ?, 'wfp')
            """, (
                product_id,
                entry["state"],
                entry["price"],
                entry["market"],
                entry["date"]
            ))
            state_prices_added += 1

    conn.commit()
    conn.close()

    print(f"[wfp] Done — {products_added} products, {prices_added} price records, {state_prices_added} state prices.")


if __name__ == "__main__":
    seed()