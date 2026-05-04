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

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/add_product", methods=["POST"])
def add_product():
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Product name required"}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, url) VALUES (?, ?)",
              (name, data.get("url", "")))
    conn.commit()
    product_id = c.lastrowid
    conn.close()
    return jsonify({"message": "Product added ✅", "id": product_id})

@app.route("/log_price", methods=["POST"])
def log_price():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO price_history (product_id, price, date) VALUES (?, ?, ?)",
              (data["product_id"], data["price"], str(date.today())))
    conn.commit()
    conn.close()
    return jsonify({"message": "Price logged ✅"})

@app.route("/products", methods=["GET"])
def get_products():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(products)

@app.route("/history/<int:product_id>", methods=["GET"])
def get_history(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM price_history WHERE product_id = ? ORDER BY date ASC",
              (product_id,))
    history = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(history)

if __name__ == "__main__":
    app.run(debug=True) 