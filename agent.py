import sqlite3
import os
import json
from groq import Groq
from dotenv import load_dotenv
from datetime import date, datetime
 
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
 
 
def get_community_price_context():
    """
    Reads community_prices submitted by real sellers.
    Returns a formatted summary per commodity showing:
    - How many sellers are reporting
    - Price range (min to max)
    - Cheapest seller and their location/state
    - Most recent submission date
    """
    conn = get_db()
    c = conn.cursor()
 
    c.execute("""
        SELECT
            cp.commodity,
            cp.price,
            cp.unit,
            cp.state,
            cp.platform,
            cp.date_submitted,
            cs.full_name,
            cs.business_name,
            cs.location,
            cs.seller_type
        FROM community_prices cp
        JOIN community_sellers cs ON cp.seller_id = cs.id
        ORDER BY cp.date_submitted DESC
    """)
    rows = c.fetchall()
    conn.close()
 
    if not rows:
        return "\n📍 COMMUNITY PRICES: No community prices submitted yet. Only NBS data available.\n"
 
    # Group by commodity
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
 
        # Cheapest seller
        cheapest = min(entries, key=lambda x: x["price"])
        seller_name = cheapest["business_name"] if cheapest["business_name"] else cheapest["full_name"]
        latest_date = max(e["date_submitted"] for e in entries)
 
        # State breakdown
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
    """
    Reads state_prices table and returns:
    - State-by-state price table per commodity
    - Top arbitrage opportunities (buy low state → sell high state)
    - Estimated profit after transport cost
    """
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
    """Classify what kind of question the user is asking."""
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
    """Extract Nigerian state mentioned in the question if any."""
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
    """
    Writes a behavior log entry for every agent question.
    Called automatically inside ask_agent() after every response.
    """
    if not commodities_mentioned:
        # Still log even if no specific commodity detected — use 'general'
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
        """, (
            session_id,
            "agent_question",
            commodity,
            question_type,
            state_mentioned,
            datetime.now().isoformat()
        ))
 
    conn.commit()
    conn.close()
 
 
def get_user_profile(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    row = c.fetchone()
 
    # Also get behavior log summary
    c.execute("""
        SELECT commodity, COUNT(*) as cnt
        FROM user_behavior_log
        WHERE session_id = ?
        GROUP BY commodity ORDER BY cnt DESC LIMIT 1
    """, (session_id,))
    top_commodity = c.fetchone()
 
    c.execute("""
        SELECT question_type, COUNT(*) as cnt
        FROM user_behavior_log
        WHERE session_id = ?
        GROUP BY question_type ORDER BY cnt DESC LIMIT 1
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
   Example: "Wholesale has the cheapest rice right now at ₦110,000. Online is the most expensive at ₦120,000."
 
3. ARBITRAGE / PROFIT QUESTION (trader asking where to buy/sell) — use this format:
   📍 BUY: [state + price]
   📍 SELL: [state + price]
   💰 PROFIT: [net profit after transport per unit]
   📊 MARGIN: [profit %]
   ⚡ DO THIS: [one clear action sentence]
 
4. COMMODITY NOT IN DATABASE — be honest and short
   Example: "Beans isn't in our system yet — we track Rice, Bread and Fuel. Want advice on any of those?"
 
5. SERIOUS BUYING DECISION — use this format, keep each part to 2 sentences max:
   📊 SITUATION: [what's happening in the market right now]
   ⚡ ACTION: [exactly what to do — be direct]
   💡 SUGGESTION: [one smart tip for their role]
   ⚠️ CONFIDENCE: [High/Medium/Low and one reason why]
   📅 UPDATED: [most recent date in the data]
 
COMMUNITY PRICE RULES:
- If community prices exist for a commodity, always mention them — they're more current than NBS data
- If a community seller is significantly cheaper or more expensive than NBS, flag it: "A seller in [location] is offering [commodity] at ₦X — that's cheaper than the NBS average"
- If no community prices exist yet, you can mention "No live seller prices yet — these are NBS verified averages"
 
IMPORTANT:
- For traders: ALWAYS mention the best arbitrage opportunity even if they didn't ask — it's your job
- Never make up prices or trends not in the data
- Always mention the cheapest state AND cheapest platform when relevant
- Speak with confidence but stay honest about data limits
- If the trend is clear say it clearly — "prices are rising fast, buy now" not "it may be advisable to consider purchasing"
- Transport costs are already factored into the net profit numbers — don't double count
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
 
    # FIX 1 — Log behavior after every agent interaction
    log_behavior(session_id, question, commodities_mentioned)
 
    return answer
 
 
def generate_user_review(session_id, commodity):
    """
    The clone function. Given a user's profile and a commodity,
    generates a star rating + written review as if the user wrote it.
    Saves to generated_reviews table and returns the result.
    """
    conn = get_db()
    c = conn.cursor()
 
    # Get user profile
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    profile = c.fetchone()
 
    # FIX 2 — Get count AND full behavior detail for this commodity
    c.execute("""
        SELECT COUNT(*) as cnt FROM user_behavior_log
        WHERE session_id = ? AND commodity = ?
    """, (session_id, commodity))
    commodity_searches = c.fetchone()["cnt"]
 
    # Get full behavior log — last 20 interactions across all commodities
    c.execute("""
        SELECT action_type, commodity, question_type, state_mentioned, timestamp
        FROM user_behavior_log
        WHERE session_id = ?
        ORDER BY timestamp DESC LIMIT 20
    """, (session_id,))
    behavior_rows = c.fetchall()
 
    # Build human-readable behavior summary
    if behavior_rows:
        behavior_summary = "What this user has actually been asking about:\n"
        for b in behavior_rows:
            line = f"- {b['question_type']} question about {b['commodity']}"
            if b['state_mentioned']:
                line += f" (mentioned {b['state_mentioned']})"
            behavior_summary += line + "\n"
    else:
        behavior_summary = "No behavior logged yet — base review on profile and price data only."
 
    # Get current price data for this commodity
    c.execute("""
        SELECT ph.price, ph.platform, ph.date, p.name
        FROM price_history ph
        JOIN products p ON ph.product_id = p.id
        WHERE p.name = ?
        ORDER BY ph.date DESC LIMIT 6
    """, (commodity,))
    recent_prices = c.fetchall()
 
    # Get state prices for arbitrage
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
 
    # Build state price summary
    state_summary = ""
    if state_prices:
        cheapest = state_prices[0]
        most_expensive = state_prices[-1]
        state_summary = f"Cheapest state: {cheapest['state']} at ₦{cheapest['price']:,.0f}. Most expensive: {most_expensive['state']} at ₦{most_expensive['price']:,.0f}."
 
    # Build profile context
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
        "consumer": "everyday Nigerian consumer who buys for their family. Speak like a regular person — use Pidgin naturally, be emotional about price increases, celebrate good prices.",
        "trader": "experienced Nigerian commodity trader who buys in bulk and resells for profit. Focus on margins, arbitrage opportunities, and market timing. Use trader language.",
        "small_business": "small business owner in Nigeria managing costs carefully. Think about inventory, cash flow, and supplier reliability. Be analytical but relatable."
    }
 
    voice = role_voice.get(role, role_voice["consumer"])
 
    # FIX 3 — Pass full behavior summary into the review prompt
    review_prompt = f"""You are simulating a market review written by a specific Nigerian user. You are their clone — you know everything about them and must write EXACTLY as they would.
 
USER PROFILE:
- Role: {role}
- State: {user_state}
- Buys: {bulk_freq}
- Cares about: {priority}
- Times on platform: {sessions}
- Times searched this commodity: {commodity_searches}
 
OBSERVED BEHAVIOR (what this user has actually been doing on the platform):
{behavior_summary}
 
CURRENT MARKET DATA FOR {commodity}:
- Latest price: ₦{latest_price:,.0f}
- Recent average: ₦{avg_price:,.0f}
- Trend: {price_trend}
- {state_summary}
 
YOUR TASK:
Write a review of the current {commodity} market AS THIS USER.
The review must reflect their actual behavior above — if they kept asking about arbitrage, their review should sound like a trader chasing margins. If they kept asking about cheapest price, sound like someone watching every kobo.
 
Rules:
1. Start with RATING: X/5 (just the number, nothing else on that line)
2. Then write the review on the next line
3. Review must be 3-5 sentences in their voice
4. Use Nigerian Pidgin naturally — not forced, just how they'd actually talk
5. Reference actual prices from the data
6. Their rating logic:
   - Consumer: rising prices = low stars, falling = high stars
   - Trader: good arbitrage opportunity = high stars regardless of direction
   - Small business: stability = high stars, volatility = low stars
7. Sound like a real person wrote this, not an AI
8. If behavior shows they were focused on a specific state or question type, reflect that in the review
 
Example format:
RATING: 3/5
E don do small. Rice price don drop from ₦118k to ₦112k for Lagos side...
"""
 
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": review_prompt}],
        model="llama-3.3-70b-versatile",
    )
 
    raw = response.choices[0].message.content.strip()
 
    # Parse rating and review text
    lines = raw.split("\n")
    star_rating = 3  # default
    review_lines = []
 
    for i, line in enumerate(lines):
        if line.startswith("RATING:"):
            try:
                star_rating = int(line.replace("RATING:", "").strip().split("/")[0])
                star_rating = max(1, min(5, star_rating))
            except:
                star_rating = 3
        else:
            if line.strip():
                review_lines.append(line.strip())
 
    review_text = " ".join(review_lines)
 
    # Determine sentiment
    if star_rating >= 4:
        sentiment = "POSITIVE"
    elif star_rating <= 2:
        sentiment = "NEGATIVE"
    else:
        sentiment = "NEUTRAL"
 
    # Save to database
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
        "id": review_id,
        "commodity": commodity,
        "star_rating": star_rating,
        "review_text": review_text,
        "sentiment": sentiment,
        "price_at_review": latest_price,
        "role": role,
        "user_state": user_state
    }
    
    
# This is called by /clone_negotiate when the clone spots a profitable deal
# and needs to message a seller on the user's behalf
 
def clone_negotiate_message(commodity, price, profile, chat_history):
    """
    Generates a negotiation message from the clone, mimicking the user's tone.
    
    Args:
        commodity: e.g. "Rice (50kg bag)"
        price: current listed price e.g. 78000
        profile: dict with role, primary_commodity, bulk_frequency, priority
        chat_history: list of past messages [{"message": ..., "sent_by": ...}]
    
    Returns:
        str: the message to send, or None if failed
    """
     
 
    # Build tone sample from past messages
    buyer_messages = [m["message"] for m in chat_history if m["sent_by"] in ("buyer", "clone")]
    tone_sample = "\n".join(buyer_messages[-5:]) if buyer_messages else "No past messages yet."
 
    role = profile.get("role", "consumer")
    bulk_freq = profile.get("bulk_frequency", "Monthly")
    priority = profile.get("priority", "Cheapest price")
 
    prompt = f"""You are acting as a market clone — an AI that negotiates on behalf of a Nigerian market buyer when they are offline.
 
The buyer's profile:
- Role: {role}
- Commodity of interest: {commodity}
- Buys in bulk: {bulk_freq}
- Priority: {priority}
 
The seller has listed {commodity} at ₦{price:,.0f}.
 
Past messages from this buyer (use these to match their tone and style):
{tone_sample}
 
Write ONE short negotiation message (2-4 sentences max) that:
1. Expresses interest in the deal
2. Tries to negotiate the price down slightly OR asks about bulk discount
3. Sounds natural and matches the buyer's tone — if they're casual, be casual; if formal, be formal
4. Does NOT mention being an AI or clone
 
Write only the message, nothing else."""
 
    try:
        response = client.messages.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Clone negotiate error: {e}")
        return None
 