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
  - Cold start (dataset baseline for new users)
  - Cross-domain (related commodity boost)
  - Multi-turn (session search history boost)
"""

import sqlite3
from datetime import datetime, date
import os
from groq import Groq
from dotenv import load_dotenv
import httpx
import urllib3
from dataset_integration import get_cold_start_ratings, get_reference_reviews

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
http_client = httpx.Client(verify=False, timeout=30.0)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"), http_client=http_client)


def get_db():
    conn = sqlite3.connect("pricewise.db")
    conn.row_factory = sqlite3.Row
    return conn


# ── Cross-domain commodity map ───────────────────────────────────────────────
CROSS_DOMAIN_MAP = {
    "rice":  ["bread", "fuel", "palm oil", "beans"],
    "bread": ["rice", "flour", "sugar", "butter"],
    "fuel":  ["rice", "generator", "kerosene", "diesel"],
    "palm oil": ["rice", "bread", "tomato"],
    "beans": ["rice", "yam", "garlic"],
    "flour": ["bread", "sugar", "butter"],
    "yam":   ["palm oil", "beans", "pepper"],
}

def get_cross_domain_commodities(query):
    """Return related commodity keywords for cross-domain boost."""
    q = query.lower()
    for key, related in CROSS_DOMAIN_MAP.items():
        if key in q:
            return related
    return []


# ── Cold start helpers ───────────────────────────────────────────────────────
def is_new_user(session_id):
    """True if user has fewer than 3 behavior log entries."""
    if not session_id:
        return True
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM user_behavior_log WHERE session_id = ?", (session_id,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count < 3


def get_cold_start_boost(commodity, query):
    """
    For new users — use dataset baseline ratings to boost
    well-rated commodity categories. Returns 0-15 bonus points.
    """
    commodity_category_map = {
        "rice": "household",
        "bread": "household",
        "fuel": "general",
        "palm oil": "household",
        "beans": "household",
        "flour": "household",
    }
    q = query.lower()
    mapped_cat = next((v for k, v in commodity_category_map.items() if k in q), "general")
    ratings = get_cold_start_ratings(mapped_cat, limit=20)
    if not ratings:
        return 0, 3.5
    avg = sum(ratings) / len(ratings)
    # Scale: avg rating 4.5+ = 15pts, 4.0+ = 10pts, 3.5+ = 5pts
    if avg >= 4.5:
        return 15, avg
    elif avg >= 4.0:
        return 10, avg
    elif avg >= 3.5:
        return 5, avg
    return 0, avg


# ── Multi-turn session history ───────────────────────────────────────────────
def get_session_search_history(session_id, limit=5):
    """Return last N commodities this user searched for."""
    if not session_id:
        return []
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT commodity FROM user_behavior_log
        WHERE session_id = ? AND action_type = 'search'
        ORDER BY timestamp DESC LIMIT ?
    """, (session_id, limit))
    rows = c.fetchall()
    conn.close()
    return [r["commodity"].lower() for r in rows if r["commodity"]]


def get_multiturn_boost(commodity, session_history):
    """
    Boost products that match user's recent search pattern.
    If user previously searched 'rice' and now searches 'beans',
    sellers who carry both get a boost.
    Returns 0-10 bonus points.
    """
    if not session_history:
        return 0
    commodity_lower = commodity.lower()
    for past_query in session_history:
        if past_query in commodity_lower or commodity_lower in past_query:
            return 10  # repeat interest in same commodity
    # Check cross-domain match with history
    for past_query in session_history:
        related = get_cross_domain_commodities(past_query)
        if any(r in commodity_lower for r in related):
            return 5  # related to something they searched before
    return 0


# ── Main search function ─────────────────────────────────────────────────────
def search_products(query, user_state=None, user_session=None, limit=10):
    """
    Search seller_products + community_prices for a query.
    Returns ranked list of up to `limit` results with scores.
    Handles: cold start, cross-domain, multi-turn, NDCG@10.
    """
    conn = get_db()
    c = conn.cursor()

    query_lower = query.lower().strip()

    # Detect scenario type
    new_user = is_new_user(user_session)
    session_history = get_session_search_history(user_session)
    cross_domain = get_cross_domain_commodities(query_lower)

    # Cold start boost values (computed once, applied per result)
    cold_boost, dataset_avg_rating = get_cold_start_boost(None, query_lower) if new_user else (0, 3.5)

    # ── Pull candidates ──────────────────────────────────────────
    c.execute("""
        SELECT
            sp.id, sp.commodity, sp.price, sp.unit, sp.platform,
            sp.quantity, sp.availability, sp.date_updated,
            cs.id as seller_id, cs.full_name, cs.business_name,
            cs.state, cs.lga, cs.area, cs.seller_type, cs.verified
        FROM seller_products sp
        JOIN community_sellers cs ON sp.seller_id = cs.id
        WHERE LOWER(sp.commodity) LIKE ?
           OR LOWER(sp.commodity) LIKE ?
        ORDER BY sp.date_updated DESC
        LIMIT 50
    """, (f"%{query_lower}%", f"{query_lower}%"))
    results = c.fetchall()

    if not results:
        c.execute("""
            SELECT
                cp.id, cp.commodity, cp.price, cp.unit, cp.platform,
                '' as quantity, 'Available' as availability,
                cp.date_submitted as date_updated,
                cs.id as seller_id, cs.full_name, cs.business_name,
                cs.state, cs.lga, cs.area, cs.seller_type, cs.verified
            FROM community_prices cp
            JOIN community_sellers cs ON cp.seller_id = cs.id
            WHERE LOWER(cp.commodity) LIKE ?
            GROUP BY cs.id, cp.commodity
            ORDER BY cp.date_submitted DESC
            LIMIT 50
        """, (f"%{query_lower}%",))
        results = c.fetchall()

    # ── Cross-domain candidates ──────────────────────────────────
    cross_results = []
    if cross_domain:
        for related_term in cross_domain[:2]:  # limit to 2 related terms
            c.execute("""
                SELECT
                    sp.id, sp.commodity, sp.price, sp.unit, sp.platform,
                    sp.quantity, sp.availability, sp.date_updated,
                    cs.id as seller_id, cs.full_name, cs.business_name,
                    cs.state, cs.lga, cs.area, cs.seller_type, cs.verified
                FROM seller_products sp
                JOIN community_sellers cs ON sp.seller_id = cs.id
                WHERE LOWER(sp.commodity) LIKE ?
                ORDER BY sp.date_updated DESC
                LIMIT 5
            """, (f"%{related_term}%",))
            cross_results.extend(c.fetchall())

    # ── Market stats ─────────────────────────────────────────────
    c.execute("""
        SELECT AVG(price) as avg_price, MIN(price) as min_price, MAX(price) as max_price
        FROM community_prices WHERE LOWER(commodity) LIKE ?
    """, (f"%{query_lower}%",))
    market = c.fetchone()
    avg_price = market["avg_price"] or 0
    min_price = market["min_price"] or 0
    max_price = market["max_price"] or 0

    conn.close()

    if not results and not cross_results:
        return [], None

    # ── Score function ───────────────────────────────────────────
    def score_result(r, is_cross_domain=False):
        score = 0.0
        reasons = []
        commodity_lower = r["commodity"].lower()

        # 1. Text relevance (0-30)
        if not is_cross_domain:
            if commodity_lower == query_lower:
                score += 30; reasons.append("exact match")
            elif commodity_lower.startswith(query_lower):
                score += 20; reasons.append("strong name match")
            elif query_lower in commodity_lower:
                score += 10; reasons.append("partial match")
        else:
            score += 5; reasons.append(f"related to {query_lower}")

        # 2. Price competitiveness (0-25)
        if avg_price > 0:
            pct = r["price"] / avg_price
            if pct <= 0.85:
                score += 25; reasons.append(f"price {round((1-pct)*100)}% below market")
            elif pct <= 0.95:
                score += 18; reasons.append("price slightly below market")
            elif pct <= 1.05:
                score += 12; reasons.append("price at market rate")
            elif pct <= 1.15:
                score += 5; reasons.append("price slightly above market")

        # 3. Recency (0-20)
        try:
            days_ago = (date.today() - date.fromisoformat(r["date_updated"][:10])).days
            if days_ago == 0:
                score += 20; reasons.append("listed today")
            elif days_ago <= 3:
                score += 15; reasons.append(f"listed {days_ago}d ago")
            elif days_ago <= 7:
                score += 8; reasons.append("listed this week")
            elif days_ago <= 30:
                score += 3; reasons.append("listed this month")
        except:
            pass

        # 4. Availability (0-15)
        avail = (r["availability"] or "").lower()
        if "in stock" in avail or avail == "available":
            score += 15; reasons.append("in stock")
        elif "limited" in avail:
            score += 7; reasons.append("limited stock")
        else:
            score += 2

        # 5. Verified seller (0-10)
        if r["verified"]:
            score += 10; reasons.append("verified seller")

        # 6. Location match (0-10)
        if user_state and r["state"]:
            if r["state"].lower() == user_state.lower():
                score += 10; reasons.append(f"seller in your state")
            else:
                score += 2

        # 7. Cold start boost (0-15) — new users get dataset-backed boost
        if new_user and cold_boost > 0:
            score += cold_boost
            reasons.append(f"cold-start boost (dataset avg: {dataset_avg_rating:.1f}★)")

        # 8. Multi-turn boost (0-10)
        mt_boost = get_multiturn_boost(r["commodity"], session_history)
        if mt_boost > 0:
            score += mt_boost
            reasons.append(f"matches your search history")

        return score, reasons

    # ── Score and combine ────────────────────────────────────────
    scored = []
    seen_ids = set()

    for r in results:
        if r["id"] in seen_ids:
            continue
        seen_ids.add(r["id"])
        score, reasons = score_result(r, is_cross_domain=False)
        scored.append(_build_result(r, score, reasons, is_cross_domain=False))

    for r in cross_results:
        if r["id"] in seen_ids:
            continue
        seen_ids.add(r["id"])
        score, reasons = score_result(r, is_cross_domain=True)
        scored.append(_build_result(r, score, reasons, is_cross_domain=True))

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:limit]
    for i, item in enumerate(top):
        item["rank"] = i + 1

    market_context = {
        "avg_price": round(avg_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "total_found": len(scored),
        "scenario": {
            "cold_start": new_user,
            "cross_domain": len(cross_results) > 0,
            "multi_turn": len(session_history) > 0,
            "related_commodities": cross_domain,
            "dataset_avg_rating": round(dataset_avg_rating, 2)
        }
    }

    return top, market_context


def _build_result(r, score, reasons, is_cross_domain=False):
    return {
        "rank": 0,
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
        "rank_reasons": reasons,
        "is_cross_domain": is_cross_domain
    }


def generate_agent_advice(query, ranked_results, market_context, user_state=None):
    """
    Contextual agent advice — cold start, cross-domain, and multi-turn aware.
    """
    if not ranked_results:
        return "Oga I no see that product for our market yet. Try another name or check back later."

    scenario = market_context.get("scenario", {})
    top3 = ranked_results[:3]
    avg = market_context.get("avg_price", 0)
    min_p = market_context.get("min_price", 0)

    results_summary = "\n".join([
        f"Rank {r['rank']}: {r['commodity']} — ₦{r['price']:,.0f}/{r['unit']} "
        f"from {r['seller_name']} ({r['state']}) | Score: {r['score']} | "
        f"{'[RELATED ITEM] ' if r.get('is_cross_domain') else ''}"
        f"Reasons: {', '.join(r['rank_reasons'])}"
        for r in top3
    ])

    scenario_note = ""
    if scenario.get("cold_start"):
        scenario_note = "NOTE: This is a new user — give extra guidance, explain prices clearly."
    elif scenario.get("multi_turn"):
        scenario_note = "NOTE: This user has searched before — reference their pattern, be more direct."
    if scenario.get("cross_domain"):
        related = scenario.get("related_commodities", [])
        scenario_note += f" Also showing related items: {', '.join(related[:3])}."

    prompt = f"""You are a smart Nigerian market price agent for PriceWise.

User searched: "{query}" | Location: {user_state or 'Unknown'}
{scenario_note}

Market: Avg ₦{avg:,.0f} | Cheapest ₦{min_p:,.0f} | {market_context.get('total_found', 0)} sellers found

Top results:
{results_summary}

Give SHORT sharp advice (3 sentences max):
1. Best deal and why
2. Cross-domain tip if related items are shown
3. One buying tip

Nigerian market tone — mix pidgin and english. Specific prices. No corporate talk."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=180,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[SEARCH AGENT] Error: {e}")
        best = top3[0]
        return (
            f"Best deal: {best['commodity']} at ₦{best['price']:,.0f}/{best['unit']} "
            f"from {best['seller_name']} in {best['state']}. "
            f"Market average dey around ₦{avg:,.0f}."
        )


def log_search_behavior(session_id, query, results_count, top_result=None):
    """Log search to behavior table for multi-turn and modeling."""
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
            session_id, query,
            top_result.get("state") if top_result else None,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SEARCH LOG] {e}")