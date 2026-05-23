from gevent import monkey
monkey.patch_all()

from flask import Flask, request, jsonify, render_template, send_from_directory , Response
from flask_cors import CORS
import sqlite3
from datetime import date
from agent import ask_agent
import queue
import threading




# SSE client registry
sse_clients = []
sse_lock = threading.Lock()

def broadcast(event_type, data):
    """Push an event to all connected SSE clients."""
    import json
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(msg)
            except:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


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
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS community_sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            business_name TEXT,
            phone TEXT,
            email TEXT,
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

    # Seller products — live listings
    c.execute('''
        CREATE TABLE IF NOT EXISTS seller_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            platform TEXT DEFAULT 'Open Market',
            quantity TEXT DEFAULT '',
            availability TEXT DEFAULT 'In Stock',
            date_added TEXT NOT NULL,
            date_updated TEXT NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')
 
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
    
    
        
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            role TEXT,
            primary_commodity TEXT,
            state TEXT,
            bulk_frequency TEXT,
            priority TEXT,
            behavior_type TEXT,
            total_sessions INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_behavior_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            action_type TEXT,
            commodity TEXT,
            question_type TEXT,
            state_mentioned TEXT,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS generated_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            commodity TEXT,
            star_rating INTEGER,
            review_text TEXT,
            sentiment TEXT,
            price_at_review REAL,
            generated_at TEXT,
            triggered_by TEXT DEFAULT 'manual'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_training (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT,
            answer TEXT,
            scenario_type TEXT,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT,
            scenario_type TEXT,
            options TEXT,
            answered INTEGER DEFAULT 0,
            answer TEXT,
            date_shown TEXT,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_style_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            example_message TEXT,
            context TEXT,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS seller_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            buyer_session_id TEXT,
            message TEXT,
            sent_by TEXT,
            chat_mode TEXT DEFAULT 'human',
            is_read INTEGER DEFAULT 0,
            saved INTEGER DEFAULT 1,
            timestamp TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS commodity_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            commodity TEXT,
            session_id TEXT,
            comment TEXT,
            star_rating INTEGER,
            sentiment TEXT,
            sent_by TEXT,
            timestamp TEXT
        )
    ''')
 
    conn.commit()
    conn.close()
 
 
init_db()

def run_migrations():
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE community_sellers ADD COLUMN email TEXT")
    except:
        pass
    conn.commit()
    conn.close()

run_migrations()


def auto_seed():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM products")
    count = c.fetchone()["cnt"]
    conn.close()
    if count == 0:
        from seed_data import seed
        seed()

auto_seed()
from dataset_integration import init_dataset
init_dataset(csv_path="amazon.csv")
from seed_wfp import seed as seed_wfp
seed_wfp()
 
 
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
        (full_name, business_name, phone, email, location, area, lga, state, seller_type, commodities, date_registered)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         
    """, (
        data.get("full_name"),
        data.get("business_name", ""),
        data.get("phone"),
        data.get("email",""),
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
    Legacy route — still logs to community_prices for agent/history use.
    Also mirrors into seller_products as initial listings.
    """
    data = request.get_json()
    seller_id = data.get("seller_id")
    state = data.get("state")
    prices = data.get("prices", [])
    today = str(date.today())
 
    if not seller_id or not state or not prices:
        return jsonify({"error": "Missing seller_id, state, or prices"}), 400
 
    conn = get_db()
    c = conn.cursor()
 
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
 
        # Log to community_prices (history)
        c.execute("""
            INSERT INTO community_prices
            (seller_id, commodity, price, unit, platform, state, date_submitted)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (seller_id, commodity, float(price), unit, platform, state, today))

        # Also upsert into seller_products (live listing)
        # If product already exists for this seller+commodity, update it
        c.execute("""
            SELECT id FROM seller_products
            WHERE seller_id = ? AND commodity = ?
        """, (seller_id, commodity))
        existing = c.fetchone()

        if existing:
            c.execute("""
                UPDATE seller_products
                SET price = ?, unit = ?, platform = ?, date_updated = ?
                WHERE seller_id = ? AND commodity = ?
            """, (float(price), unit, platform, today, seller_id, commodity))
        else:
            c.execute("""
                INSERT INTO seller_products
                (seller_id, commodity, price, unit, platform, quantity, availability, date_added, date_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (seller_id, commodity, float(price), unit, platform, '', 'In Stock', today, today))

        inserted += 1
 
    conn.commit()
    conn.close()
    
    
    broadcast('price_updated', {'seller_id': seller_id})
 
    return jsonify({"message": f"{inserted} price(s) submitted successfully", "inserted": inserted})


# ══════════════════════════════════════════════════════════
#  SELLER PRODUCT MANAGEMENT — new routes
# ══════════════════════════════════════════════════════════

@app.route("/seller/products/<int:seller_id>")
def get_seller_products(seller_id):
    """Returns all live product listings for a seller."""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM community_sellers WHERE id = ?", (seller_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "Seller not found"}), 404

    c.execute("""
        SELECT id, commodity, price, unit, platform, quantity, availability,
               date_added, date_updated
        FROM seller_products
        WHERE seller_id = ?
        ORDER BY date_updated DESC
    """, (seller_id,))
    rows = c.fetchall()
    conn.close()

    return jsonify([{
        "id": r["id"],
        "commodity": r["commodity"],
        "price": r["price"],
        "unit": r["unit"],
        "platform": r["platform"],
        "quantity": r["quantity"],
        "availability": r["availability"],
        "date_added": r["date_added"],
        "date_updated": r["date_updated"]
    } for r in rows])


@app.route("/seller/add_product", methods=["POST"])
def seller_add_product():
    """Seller adds a new product listing to their profile."""
    data = request.get_json()
    seller_id = data.get("seller_id")
    commodity = data.get("commodity", "").strip()
    price = data.get("price")
    unit = data.get("unit", "").strip()
    platform = data.get("platform", "Open Market")
    quantity = data.get("quantity", "").strip()
    availability = data.get("availability", "In Stock")
    today = str(date.today())

    if not seller_id or not commodity or not price or not unit:
        return jsonify({"error": "Missing required fields: seller_id, commodity, price, unit"}), 400

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, state FROM community_sellers WHERE id = ?", (seller_id,))
    seller = c.fetchone()
    if not seller:
        conn.close()
        return jsonify({"error": "Seller not found"}), 404

    # Check for duplicate commodity for this seller
    c.execute("""
        SELECT id FROM seller_products
        WHERE seller_id = ? AND LOWER(commodity) = LOWER(?)
    """, (seller_id, commodity))
    if c.fetchone():
        conn.close()
        return jsonify({"error": f"You already have a listing for '{commodity}'. Edit it instead."}), 409

    c.execute("""
        INSERT INTO seller_products
        (seller_id, commodity, price, unit, platform, quantity, availability, date_added, date_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (seller_id, commodity, float(price), unit, platform, quantity, availability, today, today))

    # Also log to community_prices for agent use
    c.execute("""
        INSERT INTO community_prices
        (seller_id, commodity, price, unit, platform, state, date_submitted)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (seller_id, commodity, float(price), unit, platform, seller["state"], today))

    conn.commit()
    new_id = c.lastrowid
    conn.close()
    
    broadcast('product_added', {'seller_id': seller_id, 'commodity': commodity})

    return jsonify({"message": "Product added", "id": new_id})


@app.route("/seller/update_product", methods=["PUT"])
def seller_update_product():
    """Seller edits an existing product listing."""
    data = request.get_json()
    product_id = data.get("product_id")
    seller_id = data.get("seller_id")
    today = str(date.today())

    if not product_id or not seller_id:
        return jsonify({"error": "Missing product_id or seller_id"}), 400

    conn = get_db()
    c = conn.cursor()

    # Verify this product belongs to this seller
    c.execute("""
        SELECT id FROM seller_products
        WHERE id = ? AND seller_id = ?
    """, (product_id, seller_id))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "Product not found or not yours"}), 404

    # Build dynamic update — only update fields that were sent
    fields = []
    values = []
    for field in ["commodity", "unit", "platform", "quantity", "availability"]:
        if field in data:
            fields.append(f"{field} = ?")
            values.append(data[field])
    if "price" in data:
        fields.append("price = ?")
        values.append(float(data["price"]))

    fields.append("date_updated = ?")
    values.append(today)
    values.extend([product_id, seller_id])

    c.execute(f"""
        UPDATE seller_products
        SET {', '.join(fields)}
        WHERE id = ? AND seller_id = ?
    """, values)

    # Log price change to community_prices if price was updated
    if "price" in data:
        c.execute("""
            SELECT commodity, unit, platform, seller_id FROM seller_products
            WHERE id = ?
        """, (product_id,))
        prod = c.fetchone()
        c.execute("SELECT state FROM community_sellers WHERE id = ?", (seller_id,))
        seller = c.fetchone()
        if prod and seller:
            c.execute("""
                INSERT INTO community_prices
                (seller_id, commodity, price, unit, platform, state, date_submitted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (seller_id, prod["commodity"], float(data["price"]),
                  prod["unit"], prod["platform"], seller["state"], today))

    conn.commit()
    conn.close()
    
    broadcast('product_updated', {'seller_id': seller_id})

    return jsonify({"message": "Product updated"})


@app.route("/seller/delete_product", methods=["DELETE"])
def seller_delete_product():
    """Seller removes a product listing."""
    data = request.get_json()
    product_id = data.get("product_id")
    seller_id = data.get("seller_id")

    if not product_id or not seller_id:
        return jsonify({"error": "Missing product_id or seller_id"}), 400

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id FROM seller_products
        WHERE id = ? AND seller_id = ?
    """, (product_id, seller_id))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "Product not found or not yours"}), 404

    c.execute("DELETE FROM seller_products WHERE id = ? AND seller_id = ?", (product_id, seller_id))
    conn.commit()
    conn.close()
    
    broadcast('product_deleted', {'seller_id': seller_id})

    return jsonify({"message": "Product deleted"})


# ══════════════════════════════════════════════════════════
#  END SELLER PRODUCT MANAGEMENT
# ══════════════════════════════════════════════════════════


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
    from agent import generate_user_review ,predict_rating
    data = request.get_json()
    session_id = data.get("session_id")
    commodity = data.get("commodity")
 
    if not session_id or not commodity:
        return jsonify({"error": "Missing session_id or commodity"}), 400
 
    result = generate_user_review(session_id, commodity)
    if not result:
        return jsonify({"error": "No price data for this commodity yet"}), 404
 
    return jsonify(result)


# ══════════════════════════════════════════════════════════
# ADD TO app.py — paste after the /generate_review route
# ══════════════════════════════════════════════════════════

@app.route("/predict_rating", methods=["POST"])
def predict_rating_route():
    from agent import predict_rating
    data = request.get_json()
    session_id = data.get("session_id")
    commodity = data.get("commodity")
    context_override = data.get("context")  # optional extra context

    if not session_id or not commodity:
        return jsonify({"error": "Missing session_id or commodity"}), 400

    result = predict_rating(session_id, commodity, context_override)
    if not result:
        return jsonify({"error": "Could not generate prediction"}), 500

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
 
    # Use seller_products for live listings
    c.execute("""
        SELECT id, commodity, price, unit, platform, quantity, availability,
               date_added, date_updated
        FROM seller_products
        WHERE seller_id = ?
        ORDER BY date_updated DESC
    """, (seller_id,))
    products = c.fetchall()

    # Fall back to community_prices if no seller_products yet
    if not products:
        c.execute("""
            SELECT commodity, price, unit, platform, date_submitted, verified_count
            FROM community_prices
            WHERE seller_id = ?
            ORDER BY date_submitted DESC
            LIMIT 20
        """, (seller_id,))
        legacy_prices = c.fetchall()
    else:
        legacy_prices = []
 
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
        "products": [{
            "id": p["id"],
            "commodity": p["commodity"],
            "price": p["price"],
            "unit": p["unit"],
            "platform": p["platform"],
            "quantity": p["quantity"],
            "availability": p["availability"],
            "date_updated": p["date_updated"]
        } for p in products],
        # Legacy fallback for old sellers who haven't migrated
        "prices": [{
            "commodity": p["commodity"],
            "price": p["price"],
            "unit": p["unit"],
            "platform": p["platform"],
            "date": p["date_submitted"],
            "verified_count": p["verified_count"]
        } for p in legacy_prices],
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
    broadcast('comment_added', {'seller_id': seller_id})
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
            COUNT(sp.id) as product_count,
            MAX(sp.date_updated) as last_active
        FROM community_sellers cs
        LEFT JOIN seller_products sp ON cs.id = sp.seller_id
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
        "product_count": r["product_count"],
        "last_active": r["last_active"]
    } for r in rows])
    
    


@app.route("/send_message", methods=["POST"])
def send_message():
    from datetime import datetime
    data = request.get_json()
    seller_id = data.get("seller_id")
    buyer_session_id = data.get("buyer_session_id")
    message = data.get("message", "").strip()
    sent_by = data.get("sent_by", "buyer")
    chat_mode = data.get("chat_mode", "human")
 
    if not seller_id or not buyer_session_id or not message:
        return jsonify({"error": "Missing fields"}), 400
 
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO seller_messages
        (seller_id, buyer_session_id, message, sent_by, chat_mode, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (seller_id, buyer_session_id, message, sent_by, chat_mode, datetime.now().isoformat()))
    conn.commit()
    msg_id = c.lastrowid
    conn.close()
    
    
    
    broadcast('message_sent', {'seller_id': seller_id, 'buyer_session_id': buyer_session_id})
 
    return jsonify({"message": "Sent", "id": msg_id})
 
 
@app.route("/get_messages/<int:seller_id>/<buyer_session_id>")
def get_messages(seller_id, buyer_session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, message, sent_by, chat_mode, is_read, saved, timestamp
        FROM seller_messages
        WHERE seller_id = ? AND buyer_session_id = ? AND saved = 1
        ORDER BY timestamp ASC
    """, (seller_id, buyer_session_id))
    rows = c.fetchall()
 
    c.execute("""
        UPDATE seller_messages SET is_read = 1
        WHERE seller_id = ? AND buyer_session_id = ? AND sent_by = 'buyer'
    """, (seller_id, buyer_session_id))
    conn.commit()
    conn.close()
 
    return jsonify([{
        "id": r["id"],
        "message": r["message"],
        "sent_by": r["sent_by"],
        "chat_mode": r["chat_mode"],
        "is_read": r["is_read"],
        "saved": r["saved"],
        "timestamp": r["timestamp"]
    } for r in rows])
 
 
@app.route("/get_seller_inbox/<int:seller_id>")
def get_seller_inbox(seller_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            buyer_session_id,
            COUNT(*) as message_count,
            SUM(CASE WHEN is_read = 0 AND sent_by = 'buyer' THEN 1 ELSE 0 END) as unread,
            MAX(timestamp) as last_message,
            MAX(CASE WHEN sent_by IN ('buyer','clone') THEN message END) as last_buyer_msg
        FROM seller_messages
        WHERE seller_id = ? AND saved = 1
        GROUP BY buyer_session_id
        ORDER BY last_message DESC
    """, (seller_id,))
    rows = c.fetchall()
    conn.close()
 
    return jsonify([{
        "buyer_session_id": r["buyer_session_id"],
        "message_count": r["message_count"],
        "unread": r["unread"],
        "last_message": r["last_message"],
        "last_buyer_msg": r["last_buyer_msg"]
    } for r in rows])
 
 
@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    data = request.get_json()
    seller_id = data.get("seller_id")
    buyer_session_id = data.get("buyer_session_id")
 
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE seller_messages SET saved = 0
        WHERE seller_id = ? AND buyer_session_id = ?
    """, (seller_id, buyer_session_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Chat cleared"})
 
 
@app.route("/clone_negotiate", methods=["POST"])
def clone_negotiate():
    from datetime import datetime
    from agent import clone_negotiate_message
 
    data = request.get_json()
    seller_id = data.get("seller_id")
    buyer_session_id = data.get("buyer_session_id")
    commodity = data.get("commodity")
    price = data.get("price")
 
    if not all([seller_id, buyer_session_id, commodity, price]):
        return jsonify({"error": "Missing fields"}), 400
 
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT message, sent_by FROM seller_messages
        WHERE seller_id = ? AND buyer_session_id = ? AND saved = 1
        ORDER BY timestamp DESC LIMIT 10
    """, (seller_id, buyer_session_id))
    history = c.fetchall()
 
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (buyer_session_id,))
    profile = c.fetchone()
    conn.close()
 
    profile_dict = dict(profile) if profile else {}
    history_list = [{"message": h["message"], "sent_by": h["sent_by"]} for h in history]
 
    clone_msg = clone_negotiate_message(commodity, price, profile_dict, history_list)
    if not clone_msg:
        return jsonify({"error": "Clone could not generate message"}), 500
 
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO seller_messages
        (seller_id, buyer_session_id, message, sent_by, chat_mode, timestamp)
        VALUES (?, ?, ?, 'clone', 'clone', ?)
    """, (seller_id, buyer_session_id, clone_msg, datetime.now().isoformat()))
    conn.commit()
    conn.close()
 
    return jsonify({"message": clone_msg, "sent_by": "clone"})



@app.route('/stream')
def stream():
    def event_stream(q):
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)

    q = queue.Queue(maxsize=10)
    with sse_lock:
        sse_clients.append(q)

    return Response(
        event_stream(q),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
    
    
# ══════════════════════════════════════════════════════════
#  CLONE CHAT ROUTES
# ══════════════════════════════════════════════════════════

from clone_chat import (
    clone_chat_response,
    generate_daily_questions,
    answer_training_question,
    get_unanswered_questions,
    get_clone_stage
)



@app.route("/clone/chat", methods=["POST"])
def clone_chat():
    from datetime import datetime
    data = request.get_json()
    session_id = data.get("session_id")
    incoming = data.get("message")
    history = data.get("history", [])
    side = data.get("side", "buyer")
    context = data.get("context", {})
    seller_id = data.get("seller_id")
    buyer_session_id = data.get("buyer_session_id")

    if not session_id or not incoming:
        return jsonify({"error": "Missing session_id or message"}), 400

    response = clone_chat_response(session_id, incoming, history, side=side, context=context, seller_id = seller_id)

    if seller_id:
        conn = get_db()
        c = conn.cursor()
        sent_by = "seller_clone" if side == "seller" else "buyer_clone"
        target_session = buyer_session_id or session_id
        c.execute("""
            INSERT INTO seller_messages
            (seller_id, buyer_session_id, message, sent_by, chat_mode, timestamp)
            VALUES (?, ?, ?, ?, 'clone', ?)
        """, (seller_id, target_session, response, sent_by, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        broadcast('message_sent', {
            'seller_id': seller_id,
            'buyer_session_id': target_session
        })

    return jsonify({"message": response, "sent_by": "clone"})

 

@app.route("/clone/questions/<session_id>")
def clone_questions(session_id):
    """Get today's unanswered training question for popup."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT primary_commodity FROM user_profiles WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    commodity = row["primary_commodity"] if row else None

    # Generate new questions if needed
    generate_daily_questions(session_id, commodity)

    # Return next unanswered one
    question = get_unanswered_questions(session_id)
    if not question:
        return jsonify({"question": None})
    return jsonify({"question": question})


@app.route("/clone/answer", methods=["POST"])
def clone_answer():
    """Save user's answer to a training question."""
    data = request.get_json()
    session_id = data.get("session_id")
    question_id = data.get("question_id")
    answer = data.get("answer")
    question_text = data.get("question_text")
    scenario_type = data.get("scenario_type")

    if not all([session_id, question_id, answer, question_text, scenario_type]):
        return jsonify({"error": "Missing fields"}), 400

    answer_training_question(session_id, question_id, answer, question_text, scenario_type)
    return jsonify({"message": "Training saved"})


@app.route("/clone/stage/<session_id>")
def clone_stage(session_id):
    """Return clone growth stage."""
    stage = get_clone_stage(session_id)
    return jsonify(stage)


@app.route("/clone/add_example", methods=["POST"])
def clone_add_example():
    """User writes an example message to train their clone's style."""
    from datetime import datetime
    data = request.get_json()
    session_id = data.get("session_id")
    example = data.get("example_message", "").strip()
    context = data.get("context", "general")

    if not session_id or not example:
        return jsonify({"error": "Missing fields"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO clone_style_examples
        (session_id, example_message, context, timestamp)
        VALUES (?, ?, ?, ?)
    """, (session_id, example, context, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"message": "Example saved"})
    


# ══════════════════════════════════════════════════════════
#  TASK B — SEARCH + RANKED RESULTS
# ══════════════════════════════════════════════════════════

from search_engine import search_products, generate_agent_advice, log_search_behavior

@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    query = data.get("query", "").strip()
    session_id = data.get("session_id")
    user_state = data.get("state")  # optional, from user profile

    if not query:
        return jsonify({"error": "Missing query"}), 400

    # If no state passed, try to get from user profile
    if not user_state and session_id:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT state FROM user_profiles WHERE session_id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        if row:
            user_state = row["state"]

    ranked, market_context = search_products(query, user_state=user_state, user_session=session_id)
    advice = generate_agent_advice(query, ranked, market_context or {}, user_state)
    log_search_behavior(session_id, query, len(ranked), ranked[0] if ranked else None)

    return jsonify({
        "query": query,
        "results": ranked,
        "market_context": market_context,
        "agent_advice": advice,
        "total": len(ranked)
    })
    
@app.route("/user_insights/<session_id>")
def user_insights(session_id):
    from agent import get_full_user_context
    ctx = get_full_user_context(session_id)
    return jsonify(ctx)



@app.route("/demo/user-agent")
def demo_user_agent():
    return render_template("demo_user_agent.html")

@app.route("/demo/recommendation")
def demo_recommendation():
    return render_template("demo_recommendation.html")


 

 
 
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)) , threaded=True)