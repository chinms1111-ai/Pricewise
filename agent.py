import sqlite3
from groq import Groq
import os
from dotenv import load_dotenv


load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_price_context():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM products")
    products = c.fetchall()
    
    context = "Here is the current commodity price data in Nigeria:\n\n"
    
    for product in products:
        context += f"Product: {product['name']}\n"
        c.execute(
            "SELECT price, platform, date FROM price_history WHERE product_id = ? ORDER BY date ASC",
            (product['id'],)
        )
        history = c.fetchall()
        for row in history:
            context += f"  {row['date']} | {row['platform']} | ₦{row['price']:,.0f}\n"
        context += "\n"
    
    conn.close()
    return context

 
 
def ask_agent(question, role="consumer"):
    context = get_price_context()
    
    role_prompts = {
        "consumer": "You are advising a regular consumer who wants to save money on everyday purchases.",
        "trader": "You are advising a trader who buys commodities in bulk and resells for profit. Think about profit margins, timing, and bulk buying opportunities.",
        "small_business": "You are advising a small business owner who needs to manage costs and plan inventory smartly."
    }
    
    role_context = role_prompts.get(role, role_prompts["consumer"])

    prompt = f"""You are PriceWise Agent, a smart price assistant for everyday Nigerians.
{role_context}

{context}

User question: {question}

Give a clear, specific recommendation based on the price trends and the user's role."""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )
    
    return response.choices[0].message.content