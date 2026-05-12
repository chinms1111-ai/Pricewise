from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import date
from agent import ask_agent
 
 
app = Flask(__name__)
CORS(app)
 
 
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'pricewise_logo.svg', mimetype='image/svg+xml')
 
 
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
            name TEXT NOT NULL,
            url TEXT
        )
    ''')
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            platform TEXT,
            date TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'consumer',
            commodities TEXT DEFAULT '[]',
            questions TEXT DEFAULT '[]',
            last_seen TEXT
        )
    ''')
 
    # community_sellers — canonical schema (full registration detail)
    c.execute('''
        CREATE TABLE IF NOT EXISTS community_sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            business_name TEXT,
            phone TEXT,
            location TEXT NOT NULL,
            area TEXT NOT NULL,
            lga TEXT NOT NULL,
            state TEXT NOT NULL,
            seller_type TEXT NOT NULL,
            commodities TEXT NOT NULL,
            date_registered TEXT,
            verified INTEGER DEFAULT 0
        )
    ''')
 
    # community_prices — prices submitted by registered sellers
    c.execute('''
        CREATE TABLE IF NOT EXISTS community_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            platform TEXT DEFAULT 'Open Market',
            state TEXT NOT NULL,
            date_submitted TEXT NOT NULL,
            verified_count INTEGER DEFAULT 0,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')
 
    # state_prices — seeded NBS state-level data for arbitrage
    c.execute('''
        CREATE TABLE IF NOT EXISTS state_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            price REAL NOT NULL,
            platform TEXT,
            date TEXT,
            source TEXT DEFAULT 'seeded',
            FOREIGN KEY (product_id) REFERENCES products (id)
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
 
 
@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question")
    role = data.get("role", "consumer")
    session_id = data.get("session_id", "default")
    history = data.get("history", [])
    answer = ask_agent(question, role, session_id, history)
    return jsonify({"answer": answer})
 
 
@app.route("/seller")
def seller():
    return render_template("seller.html")
 
 
@app.route("/register_seller", methods=["POST"])
def register_seller():
    data = request.get_json()
    today = str(date.today())
 
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO community_sellers
        (full_name, business_name, phone, location, area, lga, state, seller_type, commodities, date_registered)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("full_name"),
        data.get("business_name", ""),
        data.get("phone"),
        data.get("location"),
        data.get("area"),
        data.get("lga"),
        data.get("state"),
        data.get("seller_type"),
        data.get("commodities"),
        today
    ))
    conn.commit()
    seller_id = c.lastrowid
    conn.close()
 
    return jsonify({"seller_id": seller_id, "message": "Registered successfully"})
 
 
@app.route("/submit_price", methods=["POST"])
def submit_price():
    """
    Seller submits their current prices after registration.
    Expects: seller_id, state, prices (list of {commodity, price, unit, platform})
    """
    data = request.get_json()
    seller_id = data.get("seller_id")
    state = data.get("state")
    prices = data.get("prices", [])  # list of {commodity, price, unit, platform}
    today = str(date.today())
 
    if not seller_id or not state or not prices:
        return jsonify({"error": "Missing seller_id, state, or prices"}), 400
 
    conn = get_db()
    c = conn.cursor()
 
    # Verify seller exists
    c.execute("SELECT id FROM community_sellers WHERE id = ?", (seller_id,))
    seller = c.fetchone()
    if not seller:
        conn.close()
        return jsonify({"error": "Seller not found"}), 404
 
    inserted = 0
    for p in prices:
        commodity = p.get("commodity")
        price = p.get("price")
        unit = p.get("unit", "")
        platform = p.get("platform", "Open Market")
 
        if not commodity or not price:
            continue
 
        c.execute("""
            INSERT INTO community_prices
            (seller_id, commodity, price, unit, platform, state, date_submitted)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (seller_id, commodity, float(price), unit, platform, state, today))
        inserted += 1
 
    conn.commit()
    conn.close()
 
    return jsonify({"message": f"{inserted} price(s) submitted successfully", "inserted": inserted})
 
 
@app.route("/community_prices")
def community_prices():
    """
    Returns recent community-submitted prices for display on the main page.
    Groups by commodity, shows seller location, price, date.
    """
    conn = get_db()
    c = conn.cursor()
 
    c.execute("""
        SELECT
            cp.commodity,
            cp.price,
            cp.unit,
            cp.platform,
            cp.state,
            cp.date_submitted,
            cp.verified_count,
            cs.full_name,
            cs.business_name,
            cs.location,
            cs.seller_type
        FROM community_prices cp
        JOIN community_sellers cs ON cp.seller_id = cs.id
        ORDER BY cp.date_submitted DESC
        LIMIT 50
    """)
    rows = c.fetchall()
    conn.close()
 
    result = []
    for r in rows:
        result.append({
            "commodity": r["commodity"],
            "price": r["price"],
            "unit": r["unit"],
            "platform": r["platform"],
            "state": r["state"],
            "date": r["date_submitted"],
            "verified_count": r["verified_count"],
            "seller_name": r["business_name"] if r["business_name"] else r["full_name"],
            "location": r["location"],
            "seller_type": r["seller_type"]
        })
 
    return jsonify(result)
 
 
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))