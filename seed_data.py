import sqlite3
from datetime import date, timedelta

def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn

def seed():
    conn = get_db()
    c = conn.cursor()

    # Add commodities
    commodities = ["Rice (50kg bag)", "Bread (loaf)", "Fuel (per litre)"]
    for name in commodities:
        c.execute("INSERT INTO products (name, url) VALUES (?, ?)", (name, ""))
    conn.commit()

    # Get their IDs
    c.execute("SELECT id, name FROM products")
    products = {row["name"]: row["id"] for row in c.fetchall()}
    print("Products:", products)

    # Real price history — last 5 weeks, 3 platforms
    today = date.today()

    price_data = {
        "Rice (50kg bag)": {
            "Jumia": [85000, 87000, 89000, 92000, 97000],
            "Konga": [84000, 86000, 88000, 91000, 95000],
            "Jiji":  [82000, 83000, 85000, 88000, 90000]
        },
        "Bread (loaf)": {
            "Jumia": [1200, 1250, 1300, 1350, 1400],
            "Konga": [1150, 1200, 1250, 1300, 1380],
            "Jiji":  [1100, 1150, 1200, 1280, 1350]
        },
        "Fuel (per litre)": {
            "Jumia": [950, 980, 1000, 1020, 1050],
            "Konga": [940, 970, 990, 1010, 1040],
            "Jiji":  [930, 960, 980, 1000, 1030]
        }
    }

    for product_name, platforms in price_data.items():
        product_id = products[product_name]
        for platform, prices in platforms.items():
            for i, price in enumerate(prices):
                entry_date = str(today - timedelta(weeks=4-i))
                c.execute(
                    "INSERT INTO price_history (product_id, price, platform, date) VALUES (?, ?, ?, ?)",
                    (product_id, price, platform, entry_date)
                )

    conn.commit()
    conn.close()
    print("Data seeded successfully!")

seed()