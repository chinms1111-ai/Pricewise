import sqlite3
import os
import json
from groq import Groq
from dotenv import load_dotenv
from datetime import date

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

def get_or_create_session(session_id, role):
    conn = get_db()
    c = conn.cursor()
    today = str(date.today())

    c.execute("SELECT * FROM user_sessions WHERE session_id = ?", (session_id,))
    session = c.fetchone()

    if not session:
        c.execute(
            "INSERT INTO user_sessions (session_id, role, commodities, questions, last_seen) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, "[]", "[]", today)
        )
        conn.commit()
        c.execute("SELECT * FROM user_sessions WHERE session_id = ?", (session_id,))
        session = c.fetchone()
    else:
        c.execute(
            "UPDATE user_sessions SET role = ?, last_seen = ? WHERE session_id = ?",
            (role, today, session_id)
        )
        conn.commit()

    conn.close()
    return session

def update_session(session_id, question, commodities_mentioned):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT questions, commodities FROM user_sessions WHERE session_id = ?", (session_id,))
    row = c.fetchone()

    questions = json.loads(row["questions"])
    commodities = json.loads(row["commodities"])

    questions.append(question)
    for commodity in commodities_mentioned:
        if commodity not in commodities:
            commodities.append(commodity)

    # Keep only last 10 questions
    questions = questions[-10:]

    c.execute(
        "UPDATE user_sessions SET questions = ?, commodities = ? WHERE session_id = ?",
        (json.dumps(questions), json.dumps(commodities), session_id)
    )
    conn.commit()
    conn.close()

def detect_commodities(question):
    keywords = {
        "Rice (50kg bag)": ["rice"],
        "Bread (loaf)": ["bread"],
        "Fuel (per litre)": ["fuel", "petrol", "pms"]
    }
    found = []
    question_lower = question.lower()
    for commodity, keys in keywords.items():
        for key in keys:
            if key in question_lower:
                found.append(commodity)
                break
    return found

def ask_agent(question, role="consumer", session_id="default"):
    context = get_price_context()
    session = get_or_create_session(session_id, role)

    past_questions = json.loads(session["questions"])
    past_commodities = json.loads(session["commodities"])

    role_prompts = {
        "consumer": "You are advising a regular consumer who wants to save money on everyday purchases.",
        "trader": "You are advising a trader who buys commodities in bulk and resells for profit. Think about profit margins, timing, and bulk buying opportunities.",
        "small_business": "You are advising a small business owner who needs to manage costs and plan inventory smartly."
    }

    role_context = role_prompts.get(role, role_prompts["consumer"])

    memory_context = ""
    if past_questions:
        memory_context = f"\nThis user has previously asked about: {', '.join(past_commodities) if past_commodities else 'nothing yet'}."
        memory_context += f"\nTheir last questions were: {'; '.join(past_questions[-3:])}."
        memory_context += "\nUse this to give more personalized advice.\n"

    prompt = f"""You are PriceWise Agent, a smart price assistant for everyday Nigerians.
{role_context}
{memory_context}
If the user is just greeting you or making small talk, respond warmly and briefly, then gently remind them you're here to help with commodity prices. Don't force price advice into every response.

{context}

User question: {question}

Give a clear, specific recommendation based on the price trends and the user's history."""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    )

    answer = response.choices[0].message.content

    commodities_mentioned = detect_commodities(question)
    update_session(session_id, question, commodities_mentioned)

    return answer