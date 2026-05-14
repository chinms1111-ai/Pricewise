from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import date
from agent import ask_agent


app = Flask(__name__)
CORS(app)


from apscheduler.schedulers.background import BackgroundScheduler
from clone_job import run_clone_job

scheduler = BackgroundScheduler()
scheduler.add_job(run_clone_job, trigger='cron', hour=8, minute=0)
scheduler.start()
 

 
 
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
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            cp.id,
            cp.seller_id,
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
    return jsonify([{
        "id": r["id"],
        "seller_id": r["seller_id"],
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
    } for r in rows])
 
 
 
 
@app.route("/save_profile", methods=["POST"])
def save_profile():
    data = request.get_json()
    session_id = data.get("session_id")
    today = str(date.today())
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM user_profiles WHERE session_id = ?", (session_id,))
    existing = c.fetchone()
    if existing:
        c.execute("""
            UPDATE user_profiles SET role=?, primary_commodity=?, state=?,
            bulk_frequency=?, priority=?, updated_at=?, total_sessions=total_sessions+1
            WHERE session_id=?
        """, (data.get("role"), data.get("primary_commodity"), data.get("state"),
              data.get("bulk_frequency"), data.get("priority"), today, session_id))
    else:
        c.execute("""
            INSERT INTO user_profiles
            (session_id, role, primary_commodity, state, bulk_frequency, priority, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (session_id, data.get("role"), data.get("primary_commodity"),
              data.get("state"), data.get("bulk_frequency"), data.get("priority"), today, today))
    conn.commit()
    conn.close()
    return jsonify({"message": "Profile saved"})
 
 
@app.route("/get_profile/<session_id>")
def get_profile(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify(None)
    return jsonify({
        "role": row["role"],
        "primary_commodity": row["primary_commodity"],
        "state": row["state"],
        "bulk_frequency": row["bulk_frequency"],
        "priority": row["priority"],
        "behavior_type": row["behavior_type"],
        "total_sessions": row["total_sessions"]
    })
 
 
@app.route("/log_behavior", methods=["POST"])
def log_behavior():
    data = request.get_json()
    from datetime import datetime
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_behavior_log
        (session_id, action_type, commodity, question_type, state_mentioned, timestamp)
        VALUES (?,?,?,?,?,?)
    """, (data.get("session_id"), data.get("action_type"), data.get("commodity"),
          data.get("question_type"), data.get("state_mentioned"),
          datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"message": "Logged"})
 
 
@app.route("/generate_review", methods=["POST"])
def generate_review():
    from agent import generate_user_review
    data = request.get_json()
    session_id = data.get("session_id")
    commodity = data.get("commodity")
 
    if not session_id or not commodity:
        return jsonify({"error": "Missing session_id or commodity"}), 400
 
    result = generate_user_review(session_id, commodity)
    if not result:
        return jsonify({"error": "No price data for this commodity yet"}), 404
 
    return jsonify(result)
 
 
@app.route("/my_reviews/<session_id>")
def my_reviews(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM generated_reviews
        WHERE session_id = ?
        ORDER BY generated_at DESC LIMIT 20
    """, (session_id,))
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        "commodity": r["commodity"],
        "star_rating": r["star_rating"],
        "review_text": r["review_text"],
        "sentiment": r["sentiment"],
        "price_at_review": r["price_at_review"],
        "generated_at": r["generated_at"]
    } for r in rows])
    
    
    
    
    
    
    
    
@app.route("/seller/profile/<int:seller_id>")
def seller_profile_page(seller_id):
    return render_template("profile.html")
 
 
@app.route("/api/seller/<int:seller_id>")
def get_seller_profile(seller_id):
    conn = get_db()
    c = conn.cursor()
 
    c.execute("SELECT * FROM community_sellers WHERE id = ?", (seller_id,))
    seller = c.fetchone()
    if not seller:
        conn.close()
        return jsonify({"error": "Seller not found"}), 404
 
    c.execute("""
        SELECT commodity, price, unit, platform, date_submitted, verified_count
        FROM community_prices
        WHERE seller_id = ?
        ORDER BY date_submitted DESC
        LIMIT 20
    """, (seller_id,))
    prices = c.fetchall()
 
    c.execute("""
        SELECT comment, star_rating, sentiment, sent_by, timestamp
        FROM commodity_comments
        WHERE seller_id = ?
        ORDER BY timestamp DESC
        LIMIT 30
    """, (seller_id,))
    comments = c.fetchall()
 
    conn.close()
 
    return jsonify({
        "seller": {
            "id": seller["id"],
            "full_name": seller["full_name"],
            "business_name": seller["business_name"],
            "location": seller["location"],
            "area": seller["area"],
            "lga": seller["lga"],
            "state": seller["state"],
            "seller_type": seller["seller_type"],
            "commodities": seller["commodities"],
            "date_registered": seller["date_registered"],
            "verified": seller["verified"]
        },
        "prices": [{
            "commodity": p["commodity"],
            "price": p["price"],
            "unit": p["unit"],
            "platform": p["platform"],
            "date": p["date_submitted"],
            "verified_count": p["verified_count"]
        } for p in prices],
        "comments": [{
            "comment": c["comment"],
            "star_rating": c["star_rating"],
            "sentiment": c["sentiment"],
            "sent_by": c["sent_by"],
            "timestamp": c["timestamp"]
        } for c in comments]
    })
 
 
@app.route("/add_comment", methods=["POST"])
def add_comment():
    data = request.get_json()
    seller_id = data.get("seller_id")
    commodity = data.get("commodity")
    comment = data.get("comment", "").strip()
    star_rating = data.get("star_rating", 0)
    session_id = data.get("session_id", "anonymous")
    sent_by = data.get("sent_by", "user")
 
    if not seller_id or not commodity or not comment:
        return jsonify({"error": "Missing seller_id, commodity, or comment"}), 400
 
    from datetime import datetime
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO commodity_comments
        (seller_id, commodity, session_id, comment, star_rating, sentiment, sent_by, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        seller_id, commodity, session_id, comment, star_rating,
        "POSITIVE" if star_rating >= 4 else ("NEGATIVE" if star_rating <= 2 else "NEUTRAL"),
        sent_by, datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "Comment saved"})
 
 
@app.route("/sellers_board")
def sellers_board():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            cs.id, cs.full_name, cs.business_name, cs.location,
            cs.area, cs.lga, cs.state, cs.seller_type,
            cs.commodities, cs.date_registered, cs.verified,
            COUNT(cp.id) as price_count,
            MAX(cp.date_submitted) as last_active
        FROM community_sellers cs
        LEFT JOIN community_prices cp ON cs.id = cp.seller_id
        GROUP BY cs.id
        ORDER BY last_active DESC
        LIMIT 50
    """)
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        "id": r["id"],
        "name": r["business_name"] if r["business_name"] else r["full_name"],
        "location": r["location"],
        "state": r["state"],
        "seller_type": r["seller_type"],
        "commodities": r["commodities"],
        "verified": r["verified"],
        "price_count": r["price_count"],
        "last_active": r["last_active"]
    } for r in rows])
    
    


 
 
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
