import sqlite3
import json
import os
from datetime import datetime, date
from groq import Groq
from dotenv import load_dotenv
import httpx
import urllib3
from dataset_integration import get_cold_start_ratings, get_reference_reviews
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

http_client = httpx.Client(verify=False, timeout=30.0)

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"), http_client=http_client)


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


def get_community_price_context():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            cp.commodity, cp.price, cp.unit, cp.state, cp.platform, cp.date_submitted,
            cs.full_name, cs.business_name, cs.location, cs.seller_type
        FROM community_prices cp
        JOIN community_sellers cs ON cp.seller_id = cs.id
        ORDER BY cp.date_submitted DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "\n📍 COMMUNITY PRICES: No community prices submitted yet. Only NBS data available.\n"

    by_commodity = {}
    for row in rows:
        commodity = row["commodity"]
        if commodity not in by_commodity:
            by_commodity[commodity] = []
        by_commodity[commodity].append(dict(row))

    summary = "\n📍 LIVE COMMUNITY PRICES (submitted by real sellers in Nigeria):\n"
    summary += "(These are real market prices from verified sellers, not NBS averages)\n\n"

    for commodity, entries in by_commodity.items():
        prices = [e["price"] for e in entries]
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        cheapest = min(entries, key=lambda x: x["price"])
        seller_name = cheapest["business_name"] if cheapest["business_name"] else cheapest["full_name"]
        latest_date = max(e["date_submitted"] for e in entries)

        state_prices = {}
        for e in entries:
            state = e["state"]
            if state not in state_prices:
                state_prices[state] = []
            state_prices[state].append(e["price"])

        summary += f"📦 {commodity} ({len(entries)} seller report{'s' if len(entries) > 1 else ''}):\n"
        summary += f"  Range: ₦{min_price:,.0f} – ₦{max_price:,.0f}\n"
        summary += f"  Average: ₦{avg_price:,.0f}\n"
        summary += f"  Cheapest: ₦{min_price:,.0f} from {seller_name} in {cheapest['location']}, {cheapest['state']}\n"
        summary += f"  Last updated: {latest_date}\n"

        if len(state_prices) > 1:
            summary += "  By state:\n"
            for state, sprices in sorted(state_prices.items(), key=lambda x: min(x[1])):
                summary += f"    {state:<18} ₦{min(sprices):,.0f} – ₦{max(sprices):,.0f}\n"

        summary += "\n"

    return summary


def get_arbitrage_context():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, name FROM products")
    products = c.fetchall()

    transport_costs = {
        "Rice (50kg bag)": 8000,
        "Bread (sliced loaf)": 150,
        "Fuel (per litre)": 50,
    }

    arbitrage_summary = "\n🗺️ STATE PRICE COMPARISON & ARBITRAGE OPPORTUNITIES:\n"
    arbitrage_summary += "(Prices as of May 2026 — Open Market)\n\n"

    opportunities = []

    for product in products:
        product_name = product['name']
        product_id = product['id']

        c.execute(
            "SELECT state, price, platform FROM state_prices WHERE product_id = ? ORDER BY price ASC",
            (product_id,)
        )
        state_rows = c.fetchall()

        if not state_rows:
            continue

        arbitrage_summary += f"📦 {product_name}:\n"
        for row in state_rows:
            arbitrage_summary += f"  {row['state']:<18} ₦{row['price']:>10,.0f}\n"

        cheapest = state_rows[0]
        most_expensive = state_rows[-1]

        raw_gap = most_expensive['price'] - cheapest['price']
        transport = transport_costs.get(product_name, 0)
        net_profit = raw_gap - transport

        if net_profit > 0:
            opportunities.append({
                "commodity": product_name,
                "buy_state": cheapest['state'],
                "buy_price": cheapest['price'],
                "sell_state": most_expensive['state'],
                "sell_price": most_expensive['price'],
                "raw_gap": raw_gap,
                "transport_cost": transport,
                "net_profit": net_profit,
                "profit_margin": round((net_profit / cheapest['price']) * 100, 1)
            })

        arbitrage_summary += (
            f"  ✅ Best opportunity: Buy in {cheapest['state']} at ₦{cheapest['price']:,.0f}, "
            f"sell in {most_expensive['state']} at ₦{most_expensive['price']:,.0f}\n"
            f"  💰 Raw gap: ₦{raw_gap:,.0f} | Transport est: ₦{transport:,.0f} | "
            f"Net profit: ₦{net_profit:,.0f} per unit\n\n"
        )

    opportunities.sort(key=lambda x: x['net_profit'], reverse=True)

    if opportunities:
        arbitrage_summary += "🏆 TOP ARBITRAGE PICKS RIGHT NOW:\n"
        for i, op in enumerate(opportunities[:3], 1):
            arbitrage_summary += (
                f"  {i}. {op['commodity']}: "
                f"{op['buy_state']} → {op['sell_state']} | "
                f"Net ₦{op['net_profit']:,.0f} profit | "
                f"{op['profit_margin']}% margin\n"
            )

    conn.close()
    return arbitrage_summary


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
                "trend": "UNKNOWN", "alert": "⚪ NO DATA", "change_percent": 0,
                "confidence": "Low", "weeks_consistent": 0, "latest_price": 0,
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

        confidence = "High" if len(prices) >= 10 else "Medium" if len(prices) >= 5 else "Low"

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
            "trend": trend, "alert": alert, "change_percent": round(change_percent, 2),
            "confidence": confidence, "weeks_consistent": weeks_consistent,
            "latest_price": last_price, "cheapest_platform": cheapest_platform,
            "first_date": dates[0], "last_date": dates[-1]
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
        "Bread (sliced loaf)": ["bread"],
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


def detect_question_type(question):
    q = question.lower()
    if any(w in q for w in ["buy", "sell", "profit", "arbitrage", "move", "trade"]):
        return "arbitrage"
    elif any(w in q for w in ["trend", "rising", "falling", "going up", "going down", "increase", "decrease"]):
        return "trend"
    elif any(w in q for w in ["cheap", "cheapest", "best price", "where", "lowest"]):
        return "sourcing"
    elif any(w in q for w in ["how much", "price", "cost", "rate"]):
        return "price_check"
    elif any(w in q for w in ["store", "stock", "inventory", "keep", "hold"]):
        return "inventory"
    else:
        return "general"


def detect_state_mentioned(question):
    states = [
        "Lagos", "Abuja", "Kano", "Rivers", "Oyo", "Kaduna", "Enugu",
        "Delta", "Anambra", "Imo", "Ogun", "Osun", "Kwara", "Benue",
        "Plateau", "Niger", "Sokoto", "Zamfara", "Kebbi", "Kogi",
        "Nasarawa", "Taraba", "Adamawa", "Gombe", "Bauchi", "Yobe",
        "Borno", "Jigawa", "Katsina", "Ekiti", "Ondo", "Edo",
        "Cross River", "Akwa Ibom", "Bayelsa", "Ebonyi", "Abia"
    ]
    q = question.lower()
    for state in states:
        if state.lower() in q:
            return state
    return None


def log_behavior(session_id, question, commodities_mentioned):
    if not commodities_mentioned:
        commodities_mentioned = ["general"]

    question_type = detect_question_type(question)
    state_mentioned = detect_state_mentioned(question)

    conn = get_db()
    c = conn.cursor()

    for commodity in commodities_mentioned:
        c.execute("""
            INSERT INTO user_behavior_log
            (session_id, action_type, commodity, question_type, state_mentioned, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, "agent_question", commodity, question_type, state_mentioned, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def get_user_profile(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    row = c.fetchone()

    c.execute("""
        SELECT commodity, COUNT(*) as cnt FROM user_behavior_log
        WHERE session_id = ? GROUP BY commodity ORDER BY cnt DESC LIMIT 1
    """, (session_id,))
    top_commodity = c.fetchone()

    c.execute("""
        SELECT question_type, COUNT(*) as cnt FROM user_behavior_log
        WHERE session_id = ? GROUP BY question_type ORDER BY cnt DESC LIMIT 1
    """, (session_id,))
    top_question = c.fetchone()

    conn.close()

    if not row:
        return "New user — no profile yet. Treat as general consumer."

    profile = f"""
USER PROFILE (built from onboarding + behavior):
- Role: {row['role']}
- Primary Commodity: {row['primary_commodity']}
- State: {row['state']}
- Buys in bulk: {row['bulk_frequency']}
- Cares most about: {row['priority']}
- Sessions on platform: {row['total_sessions']}
- Most searched commodity: {top_commodity['commodity'] if top_commodity else 'unknown'}
- Most common question type: {top_question['question_type'] if top_question else 'unknown'}

Adapt your tone, recommendations, and review generation to match this user's profile exactly.
"""
    return profile


def ask_agent(question, role="consumer", session_id="default", history=[]):
    context = get_price_context()
    trends = analyze_trends()
    arbitrage = get_arbitrage_context()
    community = get_community_price_context()
    user_profile = get_user_profile(session_id)
    session = get_or_create_session(session_id, role)

    past_questions = json.loads(session["questions"])
    past_commodities = json.loads(session["commodities"])

    role_prompts = {
        "consumer": "You are advising a regular consumer who wants to save money on everyday purchases. Tell them the cheapest state or platform to buy from when relevant. If community prices are available, prefer them over NBS averages as they're more current.",
        "trader": "You are advising a trader who buys commodities in bulk and resells for profit. Always think about arbitrage — buying cheap in one state and selling high in another. Give them specific profit numbers. Cross-reference community prices with NBS data — if a community seller is cheaper than NBS data, flag that as an opportunity.",
        "small_business": "You are advising a small business owner who needs to manage costs, plan inventory, and maximize profit margins. Use the state price gaps to show them how to source cheaper. Community prices show real available supply right now."
    }

    role_context = role_prompts.get(role, role_prompts["consumer"])

    memory_context = ""
    if past_questions:
        memory_context = f"\nThis user has previously asked about: {', '.join(past_commodities) if past_commodities else 'nothing yet'}."
        memory_context += f"\nTheir last questions were: {'; '.join(past_questions[-3:])}."
        memory_context += "\nUse this to give more personalized advice.\n"

    trend_summary = "\n📊 VERIFIED MARKET TRENDS:\n"
    for commodity, data in trends.items():
        trend_summary += (
            f"\n{commodity}:\n"
            f"  - Trend: {data['trend']} ({data['change_percent']}% change)\n"
            f"  - Alert Level: {data['alert']}\n"
            f"  - Confidence: {data['confidence']}\n"
            f"  - Consistent for: {data['weeks_consistent']} weeks\n"
            f"  - Cheapest now: {data['cheapest_platform']}\n"
            f"  - Data period: {data.get('first_date', 'N/A')} to {data.get('last_date', 'N/A')}\n"
        )

    prompt = f"""You are PriceWise Agent — a smart, street-aware market assistant built for everyday Nigerians. You talk like a knowledgeable friend who understands the Nigerian market, not like a formal report generator.

YOUR PERSONALITY:
- Warm, direct and confident
- Short responses by default — get to the point fast
- Nigerian in tone — you understand how markets work here
- Honest — if you don't have data on something, say so simply and suggest what you do track
- Never generate long essays unless the user is making a serious money decision

YOUR ROLE CONTEXT:
{role_context}

DEEP USER PROFILE:
{user_profile}

WHAT YOU KNOW ABOUT THIS USER (session memory):
{memory_context if memory_context else "New user — no history yet."}

VERIFIED MARKET TRENDS RIGHT NOW:
{trend_summary}

STATE PRICE DATA & ARBITRAGE INTELLIGENCE:
{arbitrage}

LIVE COMMUNITY PRICES (from real sellers on the platform):
{community}

FULL NBS PRICE HISTORY:
{context}

HOW TO RESPOND:

1. SMALL TALK OR GREETINGS — just be friendly and brief, mention you're here for market prices

2. SIMPLE PRICE QUESTION — 2 sentences max, direct answer

3. ARBITRAGE / PROFIT QUESTION — use this format:
   📍 BUY: [state + price]
   📍 SELL: [state + price]
   💰 PROFIT: [net profit after transport per unit]
   📊 MARGIN: [profit %]
   ⚡ DO THIS: [one clear action sentence]

4. COMMODITY NOT IN DATABASE — be honest and short

5. SERIOUS BUYING DECISION — use this format:
   📊 SITUATION: [what's happening in the market right now]
   ⚡ ACTION: [exactly what to do]
   💡 SUGGESTION: [one smart tip for their role]
   ⚠️ CONFIDENCE: [High/Medium/Low and one reason why]
   📅 UPDATED: [most recent date in the data]

COMMUNITY PRICE RULES:
- If community prices exist, always mention them
- Flag when community price differs significantly from NBS
- If none: "No live seller prices yet — these are NBS verified averages"

IMPORTANT:
- For traders: ALWAYS mention the best arbitrage opportunity
- Never make up prices or trends not in the data
- Always mention cheapest state AND cheapest platform when relevant
- Transport costs are already factored into net profit — don't double count
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
    log_behavior(session_id, question, commodities_mentioned)

    return answer


def generate_user_review(session_id, commodity):
    ctx = get_full_user_context(session_id)
    profile = ctx["profile"]
    commodity_searches = sum(count for name, count in ctx.get("top_commodities", []) if name == commodity)

    top_commodities = ctx.get("top_commodities", [])
    top_questions = ctx.get("top_question_types", [])
    if top_commodities:
        behavior_summary = "What this user has actually been asking about:\n"
        for name, count in top_commodities:
            behavior_summary += f"- searched {name} {count} times\n"
        for qtype, count in top_questions:
            behavior_summary += f"- {qtype} questions ({count} times)\n"
    else:
        behavior_summary = "No behavior logged yet — base review on profile and price data only."

    # ── DATASET: get reference review style ──────────────────────────────────
    # Map commodity to dataset category
    commodity_category_map = {
        "Rice (50kg bag)": "household",
        "Bread (sliced loaf)": "household",
        "Fuel (per litre)": "general",
    }
    mapped_cat = commodity_category_map.get(commodity, "general")
    refs = get_reference_reviews(mapped_cat, limit=2)
    ref_style = refs[0]["review_content"][:120] if refs else ""
    style_hint = f"Reference review style (match this tone/length, not content): \"{ref_style}\"" if ref_style else ""
    # ─────────────────────────────────────────────────────────────────────────

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT ph.price, ph.platform, ph.date, p.name
        FROM price_history ph
        JOIN products p ON ph.product_id = p.id
        WHERE p.name = ?
        ORDER BY ph.date DESC LIMIT 6
    """, (commodity,))
    recent_prices = c.fetchall()

    c.execute("""
        SELECT sp.state, sp.price
        FROM state_prices sp
        JOIN products p ON sp.product_id = p.id
        WHERE p.name = ?
        ORDER BY sp.price ASC
    """, (commodity,))
    state_prices = c.fetchall()
    conn.close()

    if not recent_prices:
        return None

    latest_price = recent_prices[0]["price"]
    prices_list = [r["price"] for r in recent_prices]
    avg_price = sum(prices_list) / len(prices_list)
    price_trend = "rising" if latest_price > avg_price else "falling" if latest_price < avg_price else "stable"

    state_summary = ""
    if state_prices:
        cheapest = state_prices[0]
        most_expensive = state_prices[-1]
        state_summary = f"Cheapest state: {cheapest['state']} at ₦{cheapest['price']:,.0f}. Most expensive: {most_expensive['state']} at ₦{most_expensive['price']:,.0f}."

    if profile:
        role = profile["role"]
        user_state = profile["state"] or "Nigeria"
        bulk_freq = profile["bulk_frequency"] or "occasionally"
        priority = profile["priority"] or "best price"
        sessions = profile["total_sessions"]
    else:
        role = "consumer"
        user_state = "Nigeria"
        bulk_freq = "occasionally"
        priority = "best price"
        sessions = 1

    role_voice = {
        "consumer": "everyday Nigerian consumer who buys for their family. Use Pidgin naturally, be emotional about price increases.",
        "trader": "experienced Nigerian commodity trader who buys in bulk. Focus on margins and arbitrage.",
        "small_business": "small business owner managing costs carefully. Think inventory and cash flow."
    }
    voice = role_voice.get(role, role_voice["consumer"])

    review_prompt = f"""You are simulating a market review written by a specific Nigerian user. Write EXACTLY as they would.

USER: Role={role}, State={user_state}, Buys={bulk_freq}, Cares about={priority}, Sessions={sessions}, Searched this commodity={commodity_searches}x

BEHAVIOR: {behavior_summary}

MARKET DATA FOR {commodity}:
- Latest: ₦{latest_price:,.0f} | Trend: {price_trend} | Avg: ₦{avg_price:,.0f}
- {state_summary}

{style_hint}

TASK: Write a review of the current {commodity} market AS THIS USER.

Rules:
1. Line 1: RATING: X/5
2. Line 2+: 3-5 sentence review in their voice
3. Use Nigerian Pidgin naturally
4. Reference actual prices
5. Rating logic: consumer=rising→low stars; trader=good arbitrage→high stars; small_business=stability→high stars
6. Sound like a real person, not AI

Example:
RATING: 3/5
E don do small. Rice price don drop from ₦118k to ₦112k for Lagos side..."""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": review_prompt}],
        model="llama-3.3-70b-versatile",
        max_tokens=250,
    )

    raw = response.choices[0].message.content.strip()
    lines = raw.split("\n")
    star_rating = 3
    review_lines = []

    for line in lines:
        if line.startswith("RATING:"):
            try:
                star_rating = int(line.replace("RATING:", "").strip().split("/")[0])
                star_rating = max(1, min(5, star_rating))
            except:
                star_rating = 3
        elif line.strip():
            review_lines.append(line.strip())

    review_text = " ".join(review_lines)
    sentiment = "POSITIVE" if star_rating >= 4 else "NEGATIVE" if star_rating <= 2 else "NEUTRAL"

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO generated_reviews
        (session_id, commodity, star_rating, review_text, sentiment, price_at_review, generated_at, triggered_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, commodity, star_rating, review_text, sentiment,
          latest_price, datetime.now().isoformat(), "manual"))
    conn.commit()
    review_id = c.lastrowid
    conn.close()

    return {
        "id": review_id, "commodity": commodity, "star_rating": star_rating,
        "review_text": review_text, "sentiment": sentiment,
        "price_at_review": latest_price, "role": role, "user_state": user_state
    }


def clone_negotiate_message(commodity, price, profile, chat_history):
    buyer_messages = [m["message"] for m in chat_history if m["sent_by"] in ("buyer", "clone")]
    tone_sample = "\n".join(buyer_messages[-5:]) if buyer_messages else "No past messages yet."

    role = profile.get("role", "consumer")
    bulk_freq = profile.get("bulk_frequency", "Monthly")
    priority = profile.get("priority", "Cheapest price")

    prompt = f"""You are a market clone — an AI negotiating on behalf of a Nigerian buyer.

Buyer: Role={role}, Commodity={commodity}, Bulk={bulk_freq}, Priority={priority}
Seller listed {commodity} at ₦{price:,.0f}.
Past buyer messages: {tone_sample}

Write ONE short negotiation message (2-4 sentences):
1. Express interest
2. Negotiate price down or ask about bulk discount
3. Match buyer's tone
4. Do NOT mention being AI

Write only the message."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Clone negotiate error: {e}")
        return None


def predict_rating(session_id, commodity, context_override=None):
    ctx = get_full_user_context(session_id)
    profile = ctx["profile"]
    past_reviews = ctx["reviews"]

    # ── DATASET: cold start baseline ─────────────────────────────────────────
    commodity_category_map = {
        "Rice (50kg bag)": "household",
        "Bread (sliced loaf)": "household",
        "Fuel (per litre)": "general",
    }
    mapped_cat = commodity_category_map.get(commodity, "general")
    baseline_ratings = get_cold_start_ratings(mapped_cat, limit=20)
    dataset_avg = round(sum(baseline_ratings) / len(baseline_ratings), 2) if baseline_ratings else 3.5
    # ─────────────────────────────────────────────────────────────────────────

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT ph.price, ph.platform, ph.date
        FROM price_history ph
        JOIN products p ON ph.product_id = p.id
        WHERE p.name = ?
        ORDER BY ph.date DESC LIMIT 6
    """, (commodity,))
    recent_prices = c.fetchall()

    c.execute("""
        SELECT sp.state, sp.price
        FROM state_prices sp
        JOIN products p ON sp.product_id = p.id
        WHERE p.name = ?
        ORDER BY sp.price ASC
    """, (commodity,))
    state_prices = c.fetchall()

    c.execute("""
        SELECT cp.price, cp.state, cs.seller_type
        FROM community_prices cp
        JOIN community_sellers cs ON cp.seller_id = cs.id
        WHERE cp.commodity = ?
        ORDER BY cp.date_submitted DESC LIMIT 10
    """, (commodity,))
    community = c.fetchall()
    conn.close()

    role = profile["role"] if profile else "consumer"
    user_state = profile["state"] if profile else "Nigeria"
    priority = profile["priority"] if profile else "best price"
    bulk_freq = profile["bulk_frequency"] if profile else "occasionally"

    price_trend = "unknown"
    volatility = "unknown"
    latest_price = None
    if recent_prices:
        prices = [r["price"] for r in recent_prices]
        latest_price = prices[0]
        avg = sum(prices) / len(prices)
        change = ((latest_price - prices[-1]) / prices[-1]) * 100 if prices[-1] else 0
        price_trend = f"{'rising' if change > 2 else 'falling' if change < -2 else 'stable'} ({change:+.1f}%)"
        spread = max(prices) - min(prices)
        volatility = f"high (₦{spread:,.0f} spread)" if spread > avg * 0.1 else "low"

    past_pattern = ""
    if past_reviews:
        avg_rating = sum(r["star_rating"] for r in past_reviews) / len(past_reviews)
        ratings_for_commodity = [r for r in past_reviews if r["commodity"] == commodity]
        past_pattern = f"User avg rating: {avg_rating:.1f}/5. "
        if ratings_for_commodity:
            last = ratings_for_commodity[0]
            past_pattern += f"Last rated {commodity}: {last['star_rating']}/5 at ₦{last['price_at_review']:,.0f}."

    commodity_hits = sum(1 for b in ctx.get("top_commodities", []) if b[0] == commodity)
    arbitrage_hits = sum(1 for qt in ctx.get("top_question_types", []) if qt[0] == "arbitrage")

    community_note = ""
    if community:
        comm_prices = [r["price"] for r in community]
        community_note = f"Community: ₦{min(comm_prices):,.0f}–₦{max(comm_prices):,.0f} ({len(community)} listings)."

    arb_note = ""
    if state_prices and len(state_prices) >= 2:
        gap = state_prices[-1]["price"] - state_prices[0]["price"]
        arb_note = f"Arbitrage gap: ₦{gap:,.0f} ({state_prices[0]['state']} → {state_prices[-1]['state']})."

    prompt = f"""You are a rating prediction engine for PriceWise (Nigerian commodity platform).

Predict what star rating (1-5) this user would give the current {commodity} market.

USER: Role={role}, State={user_state}, Bulk={bulk_freq}, Priority={priority}
Behavior: searched {commodity} {commodity_hits}x, arbitrage questions={arbitrage_hits}
Dataset baseline avg rating for similar products: {dataset_avg}/5

MARKET: Price=₦{f"{latest_price:,.0f}" if latest_price else "N/A"}, Trend={price_trend}, Volatility={volatility}
{community_note} {arb_note}
Past pattern: {past_pattern if past_pattern else "No past reviews."}
{f"Context: {context_override}" if context_override else ""}

RATING LOGIC:
- consumer: rising→low stars, falling→high stars
- trader: big arbitrage gap→high stars regardless of direction
- small_business: stable→high stars, volatile→low stars

OUTPUT (strictly):
PREDICTED_RATING: X
CONFIDENCE: High|Medium|Low
REASONING: [2-3 sentences max]
FACTORS: [3-4 comma-separated factors]"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()

        result = {
            "predicted_rating": 3, "confidence": "Medium",
            "reasoning": "Based on current market data and your profile.",
            "factors": [], "commodity": commodity, "role": role,
            "user_state": user_state, "latest_price": latest_price,
            "dataset_baseline": dataset_avg
        }

        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("PREDICTED_RATING:"):
                try:
                    val = int(line.split(":")[1].strip().split("/")[0])
                    result["predicted_rating"] = max(1, min(5, val))
                except:
                    pass
            elif line.startswith("CONFIDENCE:"):
                result["confidence"] = line.split(":")[1].strip()
            elif line.startswith("REASONING:"):
                result["reasoning"] = line.split(":", 1)[1].strip()
            elif line.startswith("FACTORS:"):
                result["factors"] = [f.strip() for f in line.split(":", 1)[1].split(",")]

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO generated_reviews
            (session_id, commodity, star_rating, review_text, sentiment, price_at_review, generated_at, triggered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, commodity, result["predicted_rating"],
            f"[PREDICTION] {result['reasoning']}",
            "POSITIVE" if result["predicted_rating"] >= 4 else ("NEGATIVE" if result["predicted_rating"] <= 2 else "NEUTRAL"),
            latest_price or 0, datetime.now().isoformat(), "predicted"
        ))
        conn.commit()
        conn.close()

        return result

    except Exception as e:
        print(f"[PREDICT RATING] Error: {e}")
        return None


def get_full_user_context(session_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    profile = c.fetchone()

    c.execute("""SELECT action_type, commodity, question_type, state_mentioned, timestamp
        FROM user_behavior_log WHERE session_id = ? ORDER BY timestamp DESC LIMIT 50
    """, (session_id,))
    behavior = c.fetchall()

    c.execute("""SELECT commodity, star_rating, sentiment, price_at_review
        FROM generated_reviews WHERE session_id = ? ORDER BY generated_at DESC LIMIT 10
    """, (session_id,))
    reviews = c.fetchall()

    c.execute("""SELECT question, answer, scenario_type
        FROM clone_training WHERE session_id = ? ORDER BY timestamp DESC LIMIT 20
    """, (session_id,))
    training = c.fetchall()

    c.execute("""SELECT message, sent_by FROM seller_messages
        WHERE buyer_session_id = ? AND sent_by = 'buyer'
        ORDER BY timestamp DESC LIMIT 20
    """, (session_id,))
    messages = c.fetchall()

    conn.close()

    from collections import Counter
    top_commodities = Counter(b["commodity"] for b in behavior).most_common(3)
    top_question_types = Counter(b["question_type"] for b in behavior).most_common(3)
    top_states = Counter(b["state_mentioned"] for b in behavior if b["state_mentioned"]).most_common(3)
    avg_rating = round(sum(r["star_rating"] for r in reviews) / len(reviews), 1) if reviews else None

    return {
        "profile": dict(profile) if profile else {},
        "top_commodities": top_commodities,
        "top_question_types": top_question_types,
        "top_states": top_states,
        "avg_rating": avg_rating,
        "reviews": [dict(r) for r in reviews],
        "training": [dict(t) for t in training],
        "messages": [dict(m) for m in messages],
        "behavior_count": len(behavior)
    }