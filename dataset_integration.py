"""
dataset_integration.py
Loads Amazon CSV into SQLite for cold start, RMSE, and BERTScore support.
No AI calls — pure SQL. Token-free.
"""

import csv
import sqlite3
import re
import os

DB_PATH = os.environ.get("DB_PATH", "pricewise.db")
CSV_PATH = os.environ.get("AMAZON_CSV", "amazon.csv")

# Map Amazon categories loosely to PriceWise commodity types
CATEGORY_MAP = {
    "grocery": "food",
    "food": "food",
    "kitchen": "household",
    "home": "household",
    "health": "health",
    "beauty": "health",
    "electronics": "electronics",
    "computers": "electronics",
    "accessories": "electronics",
    "mobiles": "electronics",
    "audio": "electronics",
    "clothing": "clothing",
    "shoes": "clothing",
    "bags": "clothing",
    "sports": "general",
    "toys": "general",
    "office": "general",
    "automotive": "general",
}

def map_category(raw_category: str) -> str:
    raw = raw_category.lower()
    for key, val in CATEGORY_MAP.items():
        if key in raw:
            return val
    return "general"

def clean_price(price_str: str) -> float:
    """Strip currency symbols and commas, return float."""
    cleaned = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def clean_rating(rating_str: str) -> float:
    try:
        return float(rating_str.strip())
    except ValueError:
        return 0.0

def run_migrations(conn):
    """Create dataset tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dataset_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE,
            product_name TEXT,
            category TEXT,
            mapped_category TEXT,
            actual_price REAL,
            discounted_price REAL,
            rating REAL,
            rating_count INTEGER
        );

        CREATE TABLE IF NOT EXISTS dataset_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            user_id TEXT,
            review_title TEXT,
            review_content TEXT,
            rating REAL,
            FOREIGN KEY(product_id) REFERENCES dataset_products(product_id)
        );
    """)
    conn.commit()

def already_seeded(conn) -> bool:
    count = conn.execute("SELECT COUNT(*) FROM dataset_products").fetchone()[0]
    return count > 0

def seed_dataset(conn, csv_path: str, limit: int = 1000):
    """
    Parse CSV and insert products + reviews.
    Handles multi-user/review rows (Amazon packs multiple users per row).
    """
    products_inserted = 0
    reviews_inserted = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            if products_inserted >= limit:
                break

            product_id = row["product_id"].strip()
            product_name = row["product_name"].strip()
            raw_category = row["category"].strip()
            mapped_cat = map_category(raw_category)
            actual_price = clean_price(row.get("actual_price", "0"))
            discounted_price = clean_price(row.get("discounted_price", "0"))
            rating = clean_rating(row.get("rating", "0"))

            rating_count_raw = re.sub(r"[^\d]", "", row.get("rating_count", "0"))
            rating_count = int(rating_count_raw) if rating_count_raw else 0

            # Insert product (skip duplicates)
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO dataset_products
                    (product_id, product_name, category, mapped_category,
                     actual_price, discounted_price, rating, rating_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (product_id, product_name, raw_category, mapped_cat,
                      actual_price, discounted_price, rating, rating_count))
                products_inserted += 1
            except Exception:
                continue

            # Parse multi-user fields (pipe or comma separated)
            user_ids = [u.strip() for u in row.get("user_id", "").split(",") if u.strip()]
            review_titles = [t.strip() for t in row.get("review_title", "").split(",") if t.strip()]
            review_contents = [c.strip() for c in row.get("review_content", "").split(",") if c.strip()]

            # Zip together what we have
            for i, uid in enumerate(user_ids):
                title = review_titles[i] if i < len(review_titles) else ""
                content = review_contents[i] if i < len(review_contents) else ""
                if not content:
                    continue
                try:
                    conn.execute("""
                        INSERT INTO dataset_reviews
                        (product_id, user_id, review_title, review_content, rating)
                        VALUES (?, ?, ?, ?, ?)
                    """, (product_id, uid, title, content, rating))
                    reviews_inserted += 1
                except Exception:
                    continue

    conn.commit()
    return products_inserted, reviews_inserted


# ── Public API used by agent.py ──────────────────────────────────────────────

def get_reference_reviews(mapped_category: str, limit: int = 5) -> list[dict]:
    """
    Pull real reviews for a category — used as BERTScore/ROUGE reference.
    Returns list of {review_content, rating}.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT dr.review_content, dr.rating
        FROM dataset_reviews dr
        JOIN dataset_products dp ON dr.product_id = dp.product_id
        WHERE dp.mapped_category = ?
        AND dr.review_content != ''
        ORDER BY RANDOM()
        LIMIT ?
    """, (mapped_category, limit)).fetchall()
    conn.close()
    return [{"review_content": r[0], "rating": r[1]} for r in rows]


def get_cold_start_ratings(mapped_category: str, limit: int = 20) -> list[float]:
    """
    For new users with no history — return avg ratings from similar category.
    Used by predict_rating() as fallback baseline.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT rating FROM dataset_products
        WHERE mapped_category = ? AND rating > 0
        ORDER BY rating_count DESC
        LIMIT ?
    """, (mapped_category, limit)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_dataset_stats() -> dict:
    """Quick summary for dashboard/debug."""
    conn = sqlite3.connect(DB_PATH)
    products = conn.execute("SELECT COUNT(*) FROM dataset_products").fetchone()[0]
    reviews = conn.execute("SELECT COUNT(*) FROM dataset_reviews").fetchone()[0]
    cats = conn.execute("""
        SELECT mapped_category, COUNT(*) as c
        FROM dataset_products GROUP BY mapped_category ORDER BY c DESC
    """).fetchall()
    conn.close()
    return {"products": products, "reviews": reviews, "by_category": dict(cats)}


def init_dataset(csv_path: str = CSV_PATH, limit: int = 1000):
    """Call this once on app startup (after DB init)."""
    conn = sqlite3.connect(DB_PATH)
    run_migrations(conn)
    if already_seeded(conn):
        print("[dataset] Already seeded, skipping.")
        conn.close()
        return
    print(f"[dataset] Seeding from {csv_path}...")
    p, r = seed_dataset(conn, csv_path, limit=limit)
    print(f"[dataset] Done — {p} products, {r} reviews inserted.")
    conn.close()


if __name__ == "__main__":
    init_dataset()
    print(get_dataset_stats())