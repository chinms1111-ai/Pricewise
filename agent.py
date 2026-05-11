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
 
 
def analyze_trends():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM products")
    products = c.fetchall()
 
    trends = {}
 
    for product in products:
        c.execute(
            "SELECT price, date FROM price_history WHERE product_id = ? ORDER BY date ASC",
            (product['id'],)
        )
        history = c.fetchall()
 
        if len(history) < 2:
            trends[product['name']] = {
                "trend": "UNKNOWN",
                "alert": "⚪ NO DATA",
                "change_percent": 0,
                "confidence": "Low",
                "weeks_consistent": 0,
                "latest_price": 0,
                "cheapest_platform": "Unknown"
            }
            continue
 
        prices = [row["price"] for row in history]
        dates = [row["date"] for row in history]
 
        first_price = prices[0]
        last_price = prices[-1]
        change_percent = ((last_price - first_price) / first_price) * 100
 
        weeks_consistent = 0
        for i in range(len(prices) - 1, 0, -1):
            if change_percent > 0 and prices[i] > prices[i-1]:
                weeks_consistent += 1
            elif change_percent < 0 and prices[i] < prices[i-1]:
                weeks_consistent += 1
            else:
                break
 
        if change_percent > 5:
            trend = "RISING"
            alert = "🔴 URGENT" if change_percent > 10 else "🟡 WATCH"
        elif change_percent < -5:
            trend = "FALLING"
            alert = "🟢 GOOD TIME TO BUY"
        else:
            trend = "STABLE"
            alert = "🟢 STABLE"
 
        if len(prices) >= 10:
            confidence = "High"
        elif len(prices) >= 5:
            confidence = "Medium"
        else:
            confidence = "Low"
 
        c.execute(
            "SELECT platform, price FROM price_history WHERE product_id = ? ORDER BY date DESC LIMIT 3",
            (product['id'],)
        )
        recent = c.fetchall()
        if recent:
            cheapest = min(recent, key=lambda x: x["price"])
            cheapest_platform = f"{cheapest['platform']} at ₦{cheapest['price']:,.0f}"
        else:
            cheapest_platform = "Unknown"
 
        trends[product['name']] = {
            "trend": trend,
            "alert": alert,
            "change_percent": round(change_percent, 2),
            "confidence": confidence,
            "weeks_consistent": weeks_consistent,
            "latest_price": last_price,
            "cheapest_platform": cheapest_platform,
            "first_date": dates[0],
            "last_date": dates[-1]
        }
 
    conn.close()
    return trends
 
 
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
 
 
def ask_agent(question, role="consumer", session_id="default", history=[]):
    context = get_price_context()
    trends = analyze_trends()
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
 
    trend_summary = "\n📊 VERIFIED MARKET TRENDS:\n"
    for commodity, data in trends.items():
        trend_summary += f"""
{commodity}:
  - Trend: {data['trend']} ({data['change_percent']}% change)
  - Alert Level: {data['alert']}
  - Confidence: {data['confidence']}
  - Consistent for: {data['weeks_consistent']} weeks
  - Cheapest now: {data['cheapest_platform']}
  - Data period: {data.get('first_date', 'N/A')} to {data.get('last_date', 'N/A')}
"""
 
    prompt = f"""You are PriceWise Agent — a smart, street-aware market assistant built for everyday Nigerians. You talk like a knowledgeable friend who understands the Nigerian market, not like a formal report generator.
 
YOUR PERSONALITY:
- Warm, direct and confident
- Short responses by default — get to the point fast
- Nigerian in tone — you understand how markets work here
- Honest — if you don't have data on something, say so simply and suggest what you do track
- Never generate long essays unless the user is making a serious money decision
 
YOUR ROLE CONTEXT:
{role_context}
 
WHAT YOU KNOW ABOUT THIS USER:
{memory_context if memory_context else "New user — no history yet."}
 
VERIFIED MARKET TRENDS RIGHT NOW:
{trend_summary}
 
FULL PRICE DATA:
{context}
 
HOW TO RESPOND:
 
1. SMALL TALK OR GREETINGS — just be friendly and brief, mention you're here for market prices
 
2. SIMPLE PRICE QUESTION — 2 sentences max, direct answer, no format needed
   Example: "Jiji has the cheapest rice right now at ₦90,000. Jumia is the most expensive at ₦97,000."
 
3. COMMODITY NOT IN DATABASE — be honest and short
   Example: "Beans isn't in our system yet — we track Rice, Bread and Fuel. Want advice on any of those?"
 
4. SERIOUS BUYING DECISION — use this format and keep each part to 2 sentences max:
 
📊 SITUATION: [what's happening in the market right now]
⚡ ACTION: [exactly what to do — be direct]
💡 SUGGESTION: [one smart tip for their role]
⚠️ CONFIDENCE: [High/Medium/Low and one reason why]
📅 UPDATED: [most recent date in the data]
 
IMPORTANT:
- Never make up prices or trends not in the data
- Always mention the cheapest platform when relevant
- Speak with confidence but stay honest about data limits
- If the trend is clear say it clearly — "prices are rising fast, buy now" not "it may be advisable to consider purchasing"
"""
 
    messages = [{"role": "system", "content": prompt}]
 
    for msg in history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
 
    messages.append({"role": "user", "content": question})
 
    response = client.chat.completions.create(
        messages=messages,
        model="llama-3.3-70b-versatile",
    )
 
    answer = response.choices[0].message.content
    commodities_mentioned = detect_commodities(question)
    update_session(session_id, question, commodities_mentioned)
 
    return answer