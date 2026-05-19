"""
clone_chat.py — PriceWise Clone Chat Brain
==========================================
Handles the AI clone that chats on behalf of users.
Learns from:
  - Past chat history
  - User-written style examples
  - Daily training question answers

Works for both buyer and seller sides.
"""

import os
import sqlite3
import json
from datetime import datetime, date
from groq import Groq
from dotenv import load_dotenv
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

http_client = httpx.Client(verify=False, timeout=30.0)


load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"), http_client=http_client)
 




def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn


# ══════════════════════════════════════════════════════════
#  CLONE PROFILE — builds full picture of who the user is
# ══════════════════════════════════════════════════════════

def get_clone_profile(session_id):
    """Fetch everything we know about this user to build the clone."""
    conn = get_db()
    c = conn.cursor()

    # Base profile
    c.execute("SELECT * FROM user_profiles WHERE session_id = ?", (session_id,))
    profile = c.fetchone()

    # Chat history (last 30 messages they sent)
    c.execute("""
        SELECT message, sent_by, timestamp FROM seller_messages
        WHERE buyer_session_id = ? AND sent_by = 'buyer'
        ORDER BY timestamp DESC LIMIT 30
    """, (session_id,))
    chat_history = c.fetchall()

    # Style examples they wrote
    c.execute("""
        SELECT example_message, context FROM clone_style_examples
        WHERE session_id = ? ORDER BY timestamp DESC LIMIT 10
    """, (session_id,))
    style_examples = c.fetchall()

    # Training answers
    c.execute("""
        SELECT question, answer, scenario_type FROM clone_training
        WHERE session_id = ? ORDER BY timestamp DESC LIMIT 20
    """, (session_id,))
    training = c.fetchall()

    conn.close()

    return {
        "profile": dict(profile) if profile else {},
        "chat_history": [dict(m) for m in chat_history],
        "style_examples": [dict(s) for s in style_examples],
        "training": [dict(t) for t in training]
    }


def build_clone_personality(clone_data, side="buyer"):
    """
    Build a system prompt that captures the user's personality,
    chat style, and learned behavior.
    """
    profile = clone_data.get("profile", {})
    history = clone_data.get("chat_history", [])
    examples = clone_data.get("style_examples", [])
    training = clone_data.get("training", [])

    role = profile.get("role", "consumer")
    state = profile.get("state", "Nigeria")
    commodity = profile.get("primary_commodity", "general commodities")
    priority = profile.get("priority", "best price")

    # Build style fingerprint from chat history
    style_samples = ""
    if history:
        samples = [m["message"] for m in history[:10]]
        style_samples = "\n".join(f'- "{s}"' for s in samples)

    # User written examples
    example_text = ""
    if examples:
        example_text = "\n".join(f'- "{e["example_message"]}" ({e["context"]})' for e in examples)

    # Training decisions
    training_text = ""
    if training:
        training_text = "\n".join(
            f'- Scenario: {t["scenario_type"]} | Question: {t["question"]} | Decision: {t["answer"]}'
            for t in training
        )

    # Determine clone growth stage
    total_signals = len(history) + len(examples) + len(training)
    if total_signals < 10:
        stage = "BEGINNER"
        stage_note = "You are still learning. Be helpful but ask clarifying questions when unsure."
    elif total_signals < 30:
        stage = "LEARNING"
        stage_note = "You have some knowledge of this user. Handle most situations but stay cautious on big decisions."
    else:
        stage = "TRAINED"
        stage_note = "You know this user well. Handle negotiations confidently in their style."

    side_instruction = ""
    if side == "buyer":
        side_instruction = """
You are acting as the BUYER's clone.
Your job is to:
- Negotiate the best price for the buyer
- Ask the right questions about product quality, quantity, availability
- Push for discounts when appropriate
- Never agree to a price above market rate without pushing back first
- If a deal looks good, signal willingness to close
"""
    else:
        side_instruction = """
You are acting as the SELLER's clone.
Your job is to:
- Respond to buyer enquiries professionally
- Defend the seller's price but allow small negotiation room (max 10% unless trained otherwise)
- Answer questions about product availability and quality
- Keep buyers engaged and interested
- Never give away too much discount without good reason
"""

    system_prompt = f"""
You are the AI clone of a Nigerian market user. You chat EXACTLY like them — same tone, same style, same energy.

=== WHO YOU ARE CLONING ===
Role: {role}
Location: {state}
Main commodity: {commodity}
Priority: {priority}
Clone stage: {stage} — {stage_note}

=== YOUR SIDE IN THIS CHAT ===
{side_instruction}

=== THEIR CHAT STYLE (learn from these) ===
{style_samples if style_samples else "No history yet — use natural Nigerian market casual tone"}

=== THEIR OWN EXAMPLE MESSAGES ===
{example_text if example_text else "None written yet"}

=== THEIR TRAINED DECISIONS ===
{training_text if training_text else "No training yet — use your best judgment"}

=== CRITICAL RULES ===
- Match their language — if they use pidgin, use pidgin. If casual english, stay casual.
- Keep messages SHORT and natural — this is a market chat not an essay
- Be direct like a Nigerian trader — no corporate talk
- Never reveal you are an AI unless directly asked
- If directly asked if you are AI or a clone, say: "I dey handle things for now, my oga go reach out soon"
- Never agree to anything you're not sure about — say "make I confirm small" and flag it
- Always push for the best deal for the person you represent
- Nigeria vibe always — "oga", "abeg", "how far", "we go sort am" are natural here

You are NOT a customer service bot. You are a real market person's digital stand-in.
"""
    return system_prompt


# ══════════════════════════════════════════════════════════
#  CLONE CHAT — main function
# ══════════════════════════════════════════════════════════

def get_seller_price_context(seller_id):
    """Fetch seller's listed prices and market prices for context."""
    if not seller_id:
        return {}
    
    conn = get_db()
    c = conn.cursor()
    
    # Seller's own listed prices
    c.execute("""
        SELECT commodity, price, unit FROM seller_products
        WHERE seller_id = ? ORDER BY date_updated DESC
    """, (seller_id,))
    products = c.fetchall()
    
    # Seller info
    c.execute("SELECT * FROM community_sellers WHERE id = ?", (seller_id,))
    seller = c.fetchone()
    
    # State market prices for seller's state
    state_prices = []
    if seller:
        c.execute("""
            SELECT cp.commodity, AVG(cp.price) as avg_price, 
                   MIN(cp.price) as min_price, MAX(cp.price) as max_price
            FROM community_prices cp
            WHERE cp.state = ?
            GROUP BY cp.commodity
        """, (seller["state"],))
        state_prices = c.fetchall()
    
    conn.close()
    
    price_context = {}
    
    if products:
        price_context["my_listings"] = [
            f"{p['commodity']}: ₦{p['price']:,.0f} per {p['unit']}"
            for p in products
        ]
        price_context["minimum_prices"] = {
            p["commodity"]: p["price"] for p in products
        }
    
    if state_prices:
        price_context["market_prices"] = [
            f"{sp['commodity']}: avg ₦{sp['avg_price']:,.0f} (min ₦{sp['min_price']:,.0f}, max ₦{sp['max_price']:,.0f})"
            for sp in state_prices
        ]
    
    if seller:
        price_context["seller_state"] = seller["state"]
        price_context["seller_email"] = seller["email"] or ""
        price_context["seller_name"] = seller["full_name"]
    
    return price_context


def detect_deal_closed(message):
    """
    Detect if a deal has been closed in the message.
    Returns True if deal closing language detected.
    """
    deal_phrases = [
        "deal", "we don agree", "i go take am", "i go buy",
        "send your account", "i accept", "okay i go pay",
        "we don settle", "done deal", "i go come",
        "payment incoming", "transfer coming", "i agree",
        "make we do am", "confirmed", "let's do it",
        "i'll take it", "sold", "we good", "sharp sharp"
    ]
    msg_lower = message.lower()
    return any(phrase in msg_lower for phrase in deal_phrases)


def extract_deal_details(chat_history, seller_price_context):
    import re
    commodity = "Not specified"
    price = "Not specified"
    quantity = "Not specified"

    if seller_price_context.get("minimum_prices"):
        commodity = list(seller_price_context["minimum_prices"].keys())[0]

    for msg in reversed(chat_history[-6:]):
        content = msg.get("content", "")

        # Quantity MUST have a unit word — match this first
        if quantity == "Not specified":
            qty_match = re.search(r'(\d+)\s*(bags?|kg|litres?|loaves?|units?)',
                                   content, re.IGNORECASE)
            if qty_match:
                quantity = f"{qty_match.group(1)} {qty_match.group(2)}"

        # Price must have ₦ sign OR be a large number (>= 100)
        if price == "Not specified":
            price_match = re.search(r'₦([\d,]+(?:\.\d+)?)', content)
            if price_match:
                price = f"₦{price_match.group(1)}"
            else:
                # Fallback — bare number but only if >= 100 (likely a price not quantity)
                bare_match = re.search(r'\b(\d{3,}(?:,\d{3})*(?:\.\d+)?)\b', content)
                if bare_match:
                    price = f"₦{bare_match.group(1)}"

        if price != "Not specified" and quantity != "Not specified":
            break

    # Final fallback — use seller's listed price
    if price == "Not specified" and seller_price_context.get("minimum_prices"):
        listed = list(seller_price_context["minimum_prices"].values())[0]
        price = f"₦{listed:,.0f}"

    return {
        "commodity": commodity,
        "price": price,
        "quantity": quantity,
        "summary": f"Your clone negotiated a deal for {commodity} at {price}" +
                   (f" for {quantity}" if quantity != "Not specified" else "") + "."
    }


def clone_chat_response(session_id, incoming_message, chat_history, 
                         side="buyer", context=None, seller_id=None):
    """
    Generate a clone response to an incoming message.
    Now price-aware and deal-detecting.
    """
    clone_data = get_clone_profile(session_id)
    
    # Get seller price context if seller_id provided
    price_context = {}
    if seller_id:
        price_context = get_seller_price_context(seller_id)
    
    system_prompt = build_clone_personality(clone_data, side=side)

    # Inject price intelligence into system prompt
    if price_context:
        price_section = "\n\n=== PRICE INTELLIGENCE — USE THIS ===\n"
        
        if price_context.get("my_listings"):
            price_section += "YOUR LISTED PRICES (NEVER GO BELOW THESE):\n"
            price_section += "\n".join(f"- {p}" for p in price_context["my_listings"])
            price_section += "\n"
        
        if price_context.get("market_prices"):
            price_section += "\nCURRENT MARKET PRICES IN YOUR STATE:\n"
            price_section += "\n".join(f"- {p}" for p in price_context["market_prices"])
            price_section += "\n"
        
        price_section += """
PRICING RULES:
- NEVER agree to a price below your listed price
- If buyer pushes too low, remind them of market rates
- You can offer max 5% discount for bulk orders only
- Always quote in Naira (₦)
- If buyer asks for price you don't have listed, check market rates and quote fairly
"""
        system_prompt += price_section

    # Add context if provided
    if context:
        context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
        system_prompt += f"\n\n=== CURRENT DEAL CONTEXT ===\n{context_str}"

    # Build messages
    messages = []
    for msg in chat_history[-10:]:
        messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })
    messages.append({"role": "user", "content": incoming_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=300,
            messages=[{"role": "system", "content": system_prompt}] + messages
        )
        reply = response.choices[0].message.content.strip()
        
        
        
        
        # Check if deal was closed
        if detect_deal_closed(incoming_message) or detect_deal_closed(reply):
            
            import re
            quantity_found = None
            for msg in reversed(chat_history[-6:] + [{"role": "user", "content": incoming_message}]):
                if not isinstance(msg, dict):
                    continue
                qty_match = re.search(r'(\d+)\s*(bags?|kg|litres?|loaves?|units?)',
                                      msg.get("content", ""), re.IGNORECASE)
                if qty_match:
                    quantity_found = f"{qty_match.group(1)} {qty_match.group(2)}"
                    break

            if not quantity_found:
                return reply + "\n\n✅ Almost done! How many units/bags are you taking so I can confirm the full order?"

            if price_context.get("seller_email") and price_context.get("seller_name"):
                safe_history = [m for m in chat_history if isinstance(m, dict)]
                deal_details = extract_deal_details(
                    safe_history + [{"role": "user", "content": incoming_message}],
                    price_context
                )
                print(f"[DEBUG] seller_email: {price_context.get('seller_email')}")
                print(f"[DEBUG] seller_name: {price_context.get('seller_name')}")
                print(f"[DEBUG] deal_details: {deal_details}")
                import threading
                from email_service import send_deal_confirmation
                buyer_session = context.get("buyer_session_id", session_id) if context else session_id
                threading.Thread(
                    target=send_deal_confirmation,
                    args=(
                        price_context["seller_email"],
                        price_context["seller_name"],
                        buyer_session,
                        deal_details,
                        seller_id
                    ),
                    daemon=True
                ).start()
                reply += "\n\n📧 *Sending deal confirmation to seller...*"
        
        
   

            # Quantity known — send email
            print(f"[DEBUG] seller_email: {price_context.get('seller_email')}")
            print(f"[DEBUG] seller_name: {price_context.get('seller_name')}")
            print(f"[DEBUG] deal detected: True")
            print(f"[DEBUG] deal_details: {deal_details}")
            if price_context.get("seller_email") and price_context.get("seller_name"):
                
                safe_history = [m for m in chat_history if isinstance(m, dict)]
                deal_details = extract_deal_details(
                    safe_history + [{"role": "user", "content": incoming_message}],
                    price_context
                )
                                
                import threading
                from email_service import send_deal_confirmation
                buyer_session = context.get("buyer_session_id", session_id) if context else session_id
                threading.Thread(
                    target=send_deal_confirmation,
                    args=(
                        price_context["seller_email"],
                        price_context["seller_name"],
                        buyer_session,
                        seller_id,
                        deal_details
                        
                    ),
                    daemon=True
                ).start()
                 
                reply += "\n\n📧 *Sending deal confirmation to seller...*"
        
         
        
        return reply
        
    except Exception as e:
        import traceback
        print(f"[CLONE CHAT] Error: {e}")
        print(f"[CLONE CHAT] Traceback: {traceback.format_exc()}")
        return "Abeg hold on small, I go sort this out."

# ══════════════════════════════════════════════════════════
#  DAILY TRAINING QUESTIONS — generates 3 per day
# ══════════════════════════════════════════════════════════

SCENARIO_TEMPLATES = [
    {
        "type": "price_negotiation",
        "question": "A buyer offered {discount}% below your asking price for {commodity}. What should your clone do?",
        "options": ["Hold the price firm", "Accept the offer", "Counter with half the discount", "Ask for bulk order first"]
    },
    {
        "type": "slow_seller",
        "question": "A seller hasn't replied in 2 hours. Your clone is waiting on a {commodity} deal. What should it do?",
        "options": ["Keep waiting", "Send a follow-up message", "Move to the next seller", "Ask for a deadline"]
    },
    {
        "type": "bulk_deal",
        "question": "A seller is offering 15% off if you buy double the quantity of {commodity}. Should your clone accept?",
        "options": ["Yes — take the bulk deal", "No — stick to original quantity", "Negotiate for triple discount", "Ask the seller to split delivery"]
    },
    {
        "type": "quality_check",
        "question": "A buyer is asking for photos and proof of {commodity} quality before paying. How should your clone respond?",
        "options": ["Send photos immediately", "Ask buyer to come inspect in person", "Offer a small sample first", "Decline — too much stress"]
    },
    {
        "type": "urgent_buyer",
        "question": "A buyer says they need {commodity} urgently and will pay 10% above your price. What should your clone do?",
        "options": ["Accept the premium price", "Stick to your normal price", "Offer express delivery at extra cost", "Confirm stock first before agreeing"]
    },
    {
        "type": "lowball_offer",
        "question": "Someone offered way too low for your {commodity} — almost half price. Clone reaction?",
        "options": ["Ignore the message", "Counter with full price firmly", "Ask what their budget actually is", "Educate them on current market price"]
    },
    {
        "type": "competitor_price",
        "question": "A buyer says another seller has {commodity} cheaper. How should your clone handle it?",
        "options": ["Match the price", "Stand your ground — your quality is better", "Ask to see the other price", "Offer a small discount to keep them"]
    },
    {
        "type": "payment_method",
        "question": "A buyer wants to pay on delivery for {commodity}. Your clone should?",
        "options": ["Accept — trust the buyer", "Reject — payment before delivery only", "Ask for 50% upfront", "Request a guarantor"]
    }
]

def generate_daily_questions(session_id, commodity=None):
    """
    Generate up to 3 training questions for the user today.
    Returns questions only if fewer than 3 have been shown today.
    """
    conn = get_db()
    c = conn.cursor()
    today = date.today().isoformat()

    # Check how many already shown today
    c.execute("""
        SELECT COUNT(*) as cnt FROM clone_questions
        WHERE session_id = ? AND date_shown = ?
    """, (session_id, today))
    shown_today = c.fetchone()["cnt"]

    if shown_today >= 3:
        conn.close()
        return []

    # Check which scenario types already used today
    c.execute("""
        SELECT scenario_type FROM clone_questions
        WHERE session_id = ? AND date_shown = ?
    """, (session_id, today))
    used_types = {row["scenario_type"] for row in c.fetchall()}

    # Pick unused scenarios
    available = [s for s in SCENARIO_TEMPLATES if s["type"] not in used_types]
    if not available:
        conn.close()
        return []

    import random
    selected = random.choice(available)
    comm = commodity or "your commodity"

    question_text = selected["question"].replace("{commodity}", comm).replace("{discount}", str(random.choice([5, 10, 15, 20])))

    now = datetime.now().isoformat()
    c.execute("""
        INSERT INTO clone_questions
        (session_id, question, scenario_type, options, answered, date_shown, timestamp)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (
        session_id,
        question_text,
        selected["type"],
        json.dumps(selected["options"]),
        today,
        now
    ))
    conn.commit()
    question_id = c.lastrowid
    conn.close()

    return [{
        "id": question_id,
        "question": question_text,
        "scenario_type": selected["type"],
        "options": selected["options"]
    }]


def answer_training_question(session_id, question_id, answer, question_text, scenario_type):
    """Save user's answer to a training question."""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()

    # Mark question as answered
    c.execute("""
        UPDATE clone_questions SET answered = 1, answer = ? WHERE id = ?
    """, (answer, question_id))

    # Save to training data
    c.execute("""
        INSERT INTO clone_training
        (session_id, question, answer, scenario_type, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, question_text, answer, scenario_type, now))

    conn.commit()
    conn.close()


def get_unanswered_questions(session_id):
    """Get any unanswered questions for today's popup."""
    conn = get_db()
    c = conn.cursor()
    today = date.today().isoformat()

    c.execute("""
        SELECT id, question, scenario_type, options
        FROM clone_questions
        WHERE session_id = ? AND date_shown = ? AND answered = 0
        ORDER BY timestamp ASC LIMIT 1
    """, (session_id, today))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "question": row["question"],
        "scenario_type": row["scenario_type"],
        "options": json.loads(row["options"])
    }


def get_clone_stage(session_id):
    """Return current clone growth stage for display."""
    clone_data = get_clone_profile(session_id)
    history = clone_data.get("chat_history", [])
    examples = clone_data.get("style_examples", [])
    training = clone_data.get("training", [])
    total = len(history) + len(examples) + len(training)

    if total < 10:
        return {"stage": "BEGINNER", "progress": total, "next": 10, "label": "Just getting started"}
    elif total < 30:
        return {"stage": "LEARNING", "progress": total, "next": 30, "label": "Learning your style"}
    else:
        return {"stage": "TRAINED", "progress": total, "next": None, "label": "Fully trained"}