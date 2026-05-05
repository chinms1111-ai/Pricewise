from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime import date

app = Flask(__name__)
CORS(app)


def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            price REAL,
            platform TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/add_product", methods=["POST"])
def add_product():
    data = request.get_json()
    name = data.get("name")
    url = data.get("url", "")

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    conn.close()

    return jsonify({"message": "Product added successfully"})


@app.route("/log_price", methods=["POST"])
def log_price():
    data = request.get_json()
    product_id = data.get("product_id")
    price = data.get("price")
    platform = data.get("platform", "Unknown")
    today = str(date.today())

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO price_history (product_id, price, platform, date) VALUES (?, ?, ?, ?)",
        (product_id, price, platform, today)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Price logged successfully"})


@app.route("/products")
def products():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    rows = c.fetchall()
    conn.close()

    return jsonify([{"id": r["id"], "name": r["name"], "url": r["url"]} for r in rows])


@app.route("/history/<int:product_id>")
def history(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT price, platform, date FROM price_history WHERE product_id = ? ORDER BY id ASC",
        (product_id,)
    )
    rows = c.fetchall()
    conn.close()
    
    return jsonify([{"price": r["price"], "platform": r["platform"], "date": r["date"]} for r in rows])
    
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))