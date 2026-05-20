"""
search_engine.py — PriceWise Task B: Product Search + Ranked Results
=====================================================================
Ranks products by relevance score for NDCG@10.
Scoring factors:
  - Text match relevance (keyword in commodity name)
  - Price competitiveness vs market average
  - Recency of listing
  - Availability status
  - Seller verification
  - Location match (if user state known)
"""

import sqlite3
from datetime import datetime, date
import os
from groq import Groq
from dotenv import load_dotenv
import httpx
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
http_client = httpx.Client(verify=False, timeout=30.0)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"), http_client=http_client)


def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn


def search_products(query, user_state=None, user_session=None, limit=10):
    """
    Search seller_products + community_prices for a query.
    Returns ranked list of up to `limit` results with scores.
    """
    conn = get_db()
    c = conn.cursor()

    query_lower = query.lower().strip()

    # ── Pull all candidate products ─────────────────────────────
    c.execute("""
        SELECT
            sp.id,
            sp.commodity,
            sp.price,
            sp.unit,
            sp.platform,
            sp.quantity,
            sp.availability,
            sp.date_updated,
            cs.id as seller_id,
            cs.full_name,
            cs.business_name,
            cs.state,
            cs.lga,
            cs.area,
            cs.seller_type,
            cs.verified
        FROM seller_products sp
        JOIN community_sellers cs ON sp.seller_id = cs.id
        WHERE LOWER(sp.commodity) LIKE ?
           OR LOWER(sp.commodity) LIKE ?
        ORDER BY sp.date_updated DESC
        LIMIT 50
    """, (f"%{query_lower}%", f"{query_lower}%"))
    results = c.fetchall()

    if not results:
        # Fallback: broader search on community_prices
        c.execute("""
            SELECT
                cp.id,
                cp.commodity,
                cp.price,
                cp.unit,
                cp.platform,
                '' as quantity,
                'Available' as availability,
                cp.date_submitted as date_updated,
                cs.id as seller_id,
                cs.full_name,
                cs.business_name,
                cs.state,
                cs.lga,
                cs.area,
                cs.seller_type,
                cs.verified
            FROM community_prices cp
            JOIN community_sellers cs ON cp.seller_id = cs.id
            WHERE LOWER(cp.commodity) LIKE ?
            GROUP BY cs.id, cp.commodity
            ORDER BY cp.date_submitted DESC
            LIMIT 50
        """, (f"%{query_lower}%",))
        results = c.fetchall()

    if not results:
        conn.close()
        return [], None

    # ── Compute market average for this commodity ───────────────
    c.execute("""
        SELECT AVG(price) as avg_price, MIN(price) as min_price, MAX(price) as max_price
        FROM community_prices
        WHERE LOWER(commodity) LIKE ?
    """, (f"%{query_lower}%",))
    market = c.fetchone()
    avg_price = market["avg_price"] or 0
    min_price = market["min_price"] or 0
    max_price = market["max_price"] or 0

    conn.close()

    # ── Score each result ────────────────────────────────────────
    scored = []
    today = date.today().isoformat()

    for r in results:
        score = 0.0
        reasons = []

        commodity_lower = r["commodity"].lower()

        # 1. Text relevance (0-30 pts)
        if commodity_lower == query_lower:
            score += 30
            reasons.append("exact match")
        elif commodity_lower.startswith(query_lower):
            score += 20
            reasons.append("strong name match")
        elif query_lower in commodity_lower:
            score += 10
            reasons.append("partial match")

        # 2. Price competitiveness vs market avg (0-25 pts)
        if avg_price > 0:
            price = r["price"]
            pct_of_avg = price / avg_price
            if pct_of_avg <= 0.85:
                score += 25
                reasons.append(f"price {round((1-pct_of_avg)*100)}% below market")
            elif pct_of_avg <= 0.95:
                score += 18
                reasons.append("price slightly below market")
            elif pct_of_avg <= 1.05:
                score += 12
                reasons.append("price at market rate")
            elif pct_of_avg <= 1.15:
                score += 5
                reasons.append("price slightly above market")
            else:
                score += 0
                reasons.append("price above market rate")

        # 3. Recency (0-20 pts)
        try:
            updated = r["date_updated"][:10]
            days_ago = (date.today() - date.fromisoformat(updated)).days
            if days_ago == 0:
                score += 20
                reasons.append("listed today")
            elif days_ago <= 3:
                score += 15
                reasons.append(f"listed {days_ago} days ago")
            elif days_ago <= 7:
                score += 8
                reasons.append("listed this week")
            elif days_ago <= 30:
                score += 3
                reasons.append("listed this month")
        except Exception:
            pass

        # 4. Availability (0-15 pts)
        availability = (r["availability"] or "").lower()
        if "in stock" in availability or availability == "available":
            score += 15
            reasons.append("in stock")
        elif "limited" in availability:
            score += 7
            reasons.append("limited stock")
        else:
            score += 2

        # 5. Verified seller (0-10 pts)
        if r["verified"]:
            score += 10
            reasons.append("verified seller")

        # 6. Location match (0-10 pts)
        if user_state and r["state"]:
            if r["state"].lower() == user_state.lower():
                score += 10
                reasons.append(f"seller in your state ({r['state']})")
            else:
                score += 2

        scored.append({
            "rank": 0,  # filled below
            "id": r["id"],
            "commodity": r["commodity"],
            "price": r["price"],
            "unit": r["unit"],
            "platform": r["platform"],
            "quantity": r["quantity"] or "Not specified",
            "availability": r["availability"] or "Available",
            "date_updated": r["date_updated"],
            "seller_id": r["seller_id"],
            "seller_name": r["business_name"] if r["business_name"] else r["full_name"],
            "state": r["state"],
            "lga": r["lga"],
            "area": r["area"],
            "seller_type": r["seller_type"],
            "verified": bool(r["verified"]),
            "score": round(score, 2),
            "rank_reasons": reasons
        })

    # ── Sort by score descending ─────────────────────────────────
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:limit]

    for i, item in enumerate(top):
        item["rank"] = i + 1

    market_context = {
        "avg_price": round(avg_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "total_found": len(scored)
    }

    return top, market_context


def generate_agent_advice(query, ranked_results, market_context, user_state=None):
    """
    Use Groq to generate contextual agent advice on the search results.
    Nigerian market style — pidgin aware, price savvy.
    """
    if not ranked_results:
        return "Oga I no see that product for our market yet. Try another name or check back later."

    top3 = ranked_results[:3]
    avg = market_context.get("avg_price", 0)
    min_p = market_context.get("min_price", 0)
    max_p = market_context.get("max_price", 0)

    results_summary = "\n".join([
        f"Rank {r['rank']}: {r['commodity']} — ₦{r['price']:,.0f}/{r['unit']} "
        f"from {r['seller_name']} ({r['state']}) | Score: {r['score']} | "
        f"Reasons: {', '.join(r['rank_reasons'])}"
        for r in top3
    ])

    prompt = f"""You are a smart Nigerian market price agent for PriceWise.

A user searched for: "{query}"
User location: {user_state or 'Unknown'}

Market overview:
- Average price: ₦{avg:,.0f}
- Cheapest found: ₦{min_p:,.0f}  
- Most expensive: ₦{max_p:,.0f}
- Total sellers found: {market_context.get('total_found', 0)}

Top 3 ranked results:
{results_summary}

Give SHORT, sharp market advice (max 3 sentences):
1. Tell them which is the best deal and why
2. Compare prices across states if different
3. Any buying tip (e.g. "bulk discount likely", "price dey high this week")

Use natural Nigerian market tone — mix of pidgin and english. 
Be specific with prices. No corporate talk. Keep it real.
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[SEARCH AGENT] Error: {e}")
        best = top3[0]
        return (
            f"Best deal I found: {best['commodity']} at ₦{best['price']:,.0f}/{best['unit']} "
            f"from {best['seller_name']} in {best['state']}. "
            f"Market average dey around ₦{avg:,.0f}."
        )


def log_search_behavior(session_id, query, results_count, top_result=None):
    """Log search action to user_behavior_log for behavioral modeling."""
    if not session_id:
        return
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_behavior_log
            (session_id, action_type, commodity, question_type, state_mentioned, timestamp)
            VALUES (?, 'search', ?, 'product_search', ?, ?)
        """, (
            session_id,
            query,
            top_result.get("state") if top_result else None,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SEARCH LOG] {e}")