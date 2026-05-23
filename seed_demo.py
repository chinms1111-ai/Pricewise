"""
seed_demo.py — PriceWise Demo Data Seeder
Seeds 50 realistic Nigerian trader profiles across 6 states
with 12 commodities, behavior logs, reviews, and price history
for hackathon judge demonstration.
"""

import sqlite3
import json
import random
from datetime import datetime, date, timedelta

DB = "pricewise.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── Nigerian names ──────────────────────────────────────
FIRST_NAMES = [
    "Emeka", "Fatima", "Chidi", "Aisha", "Tunde", "Ngozi", "Musa",
    "Chioma", "Yusuf", "Adaeze", "Babatunde", "Kemi", "Ibrahim",
    "Amaka", "Segun", "Hauwa", "Obinna", "Sade", "Aliyu", "Nneka",
    "Rotimi", "Zainab", "Chukwuemeka", "Blessing", "Usman", "Ifeoma",
    "Damilola", "Rukayat", "Nnamdi", "Tolani", "Garba", "Chinwe",
    "Adewale", "Nkechi", "Salisu", "Ebele", "Kazeem", "Ogochukwu",
    "Temitope", "Halima", "Ifeanyi", "Bunmi", "Abdullahi", "Chiamaka",
    "Rasheed", "Uchechi", "Lanre", "Amina", "Chinedu", "Folake"
]

LAST_NAMES = [
    "Okafor", "Abdullahi", "Adeyemi", "Musa", "Okonkwo", "Bello",
    "Eze", "Yusuf", "Adesanya", "Nwosu", "Garba", "Obiora",
    "Salami", "Chukwu", "Ibrahim", "Obi", "Umar", "Adeleke",
    "Nwachukwu", "Aliyu", "Fashola", "Okeke", "Mohammed", "Adebayo",
    "Onyeka", "Suleiman", "Afolabi", "Igwe", "Lawal", "Agu"
]

BUSINESS_NAMES = [
    "Grace Stores", "Alhaji Trading", "Mama Put Supplies", "ChiChi Enterprises",
    "Tunde & Sons", "Fatima Goods", "Emeka Wholesale", "Lagos Best Prices",
    "Kano Fresh Market", "Abuja Express", "PH Traders", "Ibadan Supplies",
    "Northern Agro", "Eastern Commodities", "Western Market Hub", "Delta Traders",
    "Sunrise Stores", "Blessed Hands Trading", "Al-Amin Wholesale", "Unity Market"
]

STATES = ["Lagos", "Kano", "Abuja", "Rivers", "Oyo", "Enugu"]

LOCATIONS = {
    "Lagos": ["Oshodi", "Alaba", "Mile 12", "Agege", "Mushin", "Surulere", "Ikeja"],
    "Kano": ["Sabon Gari", "Kurmi Market", "Kano Central", "Fagge", "Nassarawa"],
    "Abuja": ["Wuse Market", "Garki", "Maitama", "Nyanya", "Kubwa"],
    "Rivers": ["Mile 1", "Mile 3", "Rumuola", "Trans Amadi", "Eleme"],
    "Oyo": ["Bodija", "Dugbe", "Ojoo", "Agbeni", "Challenge"],
    "Enugu": ["Ogbete", "Coal Camp", "New Haven", "Independence Layout", "Abakpa"]
}

LGAS = {
    "Lagos": ["Oshodi-Isolo", "Alimosho", "Kosofe", "Agege", "Mushin"],
    "Kano": ["Kano Municipal", "Fagge", "Nassarawa", "Tarauni", "Gwale"],
    "Abuja": ["Abuja Municipal", "Gwagwalada", "Kuje", "Bwari", "Kwali"],
    "Rivers": ["Port Harcourt", "Obio-Akpor", "Eleme", "Ikwerre", "Etche"],
    "Oyo": ["Ibadan North", "Ibadan South-West", "Akinyele", "Lagelu", "Ona-Ara"],
    "Enugu": ["Enugu North", "Enugu South", "Igbo-Eze North", "Udi", "Nkanu"]
}

SELLER_TYPES = ["Wholesaler", "Retailer", "Individual"]

COMMODITIES = [
    "Rice (50kg bag)",
    "Bread (sliced loaf)",
    "Fuel (per litre)",
    "Eggs (crate of 30)",
    "Chicken (per kg)",
    "Palm Oil (per litre)",
    "Garri (per kg)",
    "Tomatoes (per basket)",
    "Beans (per kg)",
    "Milk (peak 900g tin)",
    "Yam (per tuber)",
    "Vegetable Oil (per litre)"
]

# Realistic price ranges per commodity per state (min, max)
PRICES = {
    "Rice (50kg bag)":      {"Lagos": (42000, 52000), "Kano": (38000, 47000), "Abuja": (45000, 55000), "Rivers": (44000, 54000), "Oyo": (40000, 50000), "Enugu": (41000, 51000)},
    "Bread (sliced loaf)":  {"Lagos": (800, 1200),    "Kano": (700, 1000),    "Abuja": (900, 1300),    "Rivers": (850, 1250),    "Oyo": (750, 1100),    "Enugu": (780, 1150)},
    "Fuel (per litre)":     {"Lagos": (750, 820),     "Kano": (760, 830),     "Abuja": (755, 815),     "Rivers": (745, 810),     "Oyo": (755, 820),     "Enugu": (760, 825)},
    "Eggs (crate of 30)":   {"Lagos": (3500, 4500),   "Kano": (3000, 4000),   "Abuja": (3800, 4800),   "Rivers": (3600, 4600),   "Oyo": (3300, 4200),   "Enugu": (3400, 4300)},
    "Chicken (per kg)":     {"Lagos": (3500, 4500),   "Kano": (3000, 4000),   "Abuja": (3800, 5000),   "Rivers": (3600, 4800),   "Oyo": (3300, 4300),   "Enugu": (3400, 4400)},
    "Palm Oil (per litre)": {"Lagos": (1800, 2500),   "Kano": (2000, 2800),   "Abuja": (2000, 2700),   "Rivers": (1600, 2200),   "Oyo": (1700, 2300),   "Enugu": (1700, 2400)},
    "Garri (per kg)":       {"Lagos": (600, 900),     "Kano": (700, 1000),    "Abuja": (650, 950),     "Rivers": (620, 920),     "Oyo": (580, 880),     "Enugu": (590, 890)},
    "Tomatoes (per basket)":{"Lagos": (8000, 15000),  "Kano": (6000, 12000),  "Abuja": (9000, 16000),  "Rivers": (8500, 14000),  "Oyo": (7000, 13000),  "Enugu": (7500, 13500)},
    "Beans (per kg)":       {"Lagos": (900, 1400),    "Kano": (800, 1200),    "Abuja": (950, 1500),    "Rivers": (920, 1420),    "Oyo": (850, 1350),    "Enugu": (870, 1370)},
    "Milk (peak 900g tin)": {"Lagos": (4500, 5500),   "Kano": (4200, 5200),   "Abuja": (4800, 5800),   "Rivers": (4600, 5600),   "Oyo": (4300, 5300),   "Enugu": (4400, 5400)},
    "Yam (per tuber)":      {"Lagos": (1500, 3000),   "Kano": (1200, 2500),   "Abuja": (1800, 3500),   "Rivers": (1600, 3200),   "Oyo": (1000, 2200),   "Enugu": (1100, 2300)},
    "Vegetable Oil (per litre)": {"Lagos": (1600, 2200), "Kano": (1500, 2100), "Abuja": (1700, 2300), "Rivers": (1650, 2250), "Oyo": (1550, 2150), "Enugu": (1580, 2180)},
}

UNITS = {
    "Rice (50kg bag)": "per bag",
    "Bread (sliced loaf)": "per loaf",
    "Fuel (per litre)": "per litre",
    "Eggs (crate of 30)": "per crate",
    "Chicken (per kg)": "per kg",
    "Palm Oil (per litre)": "per litre",
    "Garri (per kg)": "per kg",
    "Tomatoes (per basket)": "per basket",
    "Beans (per kg)": "per kg",
    "Milk (peak 900g tin)": "per tin",
    "Yam (per tuber)": "per tuber",
    "Vegetable Oil (per litre)": "per litre",
}

REVIEW_TEMPLATES = {
    "Rice (50kg bag)": [
        "This rice price don change again o. Last month na {old_price}, now dem dey sell {price}. The quality still good sha.",
        "Oga sell am {price} per bag. E be like say the Kano supply don reduce. Make una buy now before price go up again.",
        "I don buy this rice for {price}. E better pass the one wey dem sell for {old_price} last month. Quality dey."
    ],
    "Bread (sliced loaf)": [
        "Bread don reach {price} for this area. The size sef don reduce small. Before na bigger size for less money.",
        "I buy this bread {price}. Fresh and soft. This seller reliable, e never give me stale bread before.",
        "The bread price for {price} fair enough. But make dem increase the size small. We dey suffer here."
    ],
    "Fuel (per litre)": [
        "Fuel don reach {price} per litre for this area. Queue still dey but e move fast. Better than last week.",
        "I fill my tank at {price} per litre. No adulteration, my car dey run smooth. This filling station reliable.",
        "NNPC station sell am {price}. Independent stations dey sell higher. If you get time, queue for NNPC."
    ],
    "Eggs (crate of 30)": [
        "Crate of egg don reach {price}. Before na {old_price} we dey buy am. Inflation don finish us for this country.",
        "Buy my eggs {price} per crate. All 30 intact, no breakage. This seller pack am well well.",
        "The eggs fresh o. I buy {price} per crate. For this price, e better pass supermarket. Market price still better."
    ],
    "Chicken (per kg)": [
        "Chicken don reach {price} per kg. Christmas price don start early this year. Make una budget well.",
        "I buy frozen chicken {price} per kg. E thaw well, no bad smell. This cold room reliable.",
        "Live chicken dey go {price} per kg. If you buy 5kg and above dem go reduce small. Good for party."
    ],
    "Palm Oil (per litre)": [
        "Palm oil don reach {price} per litre. The colour red red, e fresh. From Benue direct.",
        "I buy {price} per litre. Pure palm oil, no adulteration. My soup taste different with this one.",
        "Palm oil price don increase to {price}. Dry season don affect the production. Stock up now."
    ],
    "Garri (per kg)": [
        "Yellow garri {price} per kg. Crunchy and dry. Good for soaking and for eba. Recommend am.",
        "I soak this garri with groundnut. Buy am {price} per kg. Value for money, e satisfying.",
        "Garri don reach {price} per kg for this market. Before na {old_price}. Everything don cost."
    ],
}

BEHAVIOR_ACTIONS = [
    "search", "price_check", "compare", "negotiate", "purchase_intent", "review_left"
]

QUESTION_TYPES = [
    "price_query", "availability_check", "quality_inquiry", "bulk_discount", "delivery_query"
]

PRIORITIES = ["best price", "quality", "proximity", "bulk deals", "trusted seller"]
BULK_FREQUENCIES = ["daily", "weekly", "bi-weekly", "monthly"]
ROLES = ["consumer", "reseller", "wholesaler", "retailer"]


def random_date(days_back=90):
    d = date.today() - timedelta(days=random.randint(0, days_back))
    return d.isoformat()

def random_ts(days_back=90):
    d = datetime.now() - timedelta(days=random.randint(0, days_back), 
                                    hours=random.randint(0, 23),
                                    minutes=random.randint(0, 59))
    return d.isoformat()


def seed_demo():
    conn = get_db()
    c = conn.cursor()

    print("🌱 Seeding demo data...")

    # ── Ensure commodities exist in products table ──
    for comm in COMMODITIES:
        c.execute("SELECT id FROM products WHERE name = ?", (comm,))
        if not c.fetchone():
            c.execute("INSERT INTO products (name, url) VALUES (?, ?)", (comm, ""))
    conn.commit()

    sellers_created = []
    sessions_created = []

    for i in range(50):
        state = random.choice(STATES)
        location = random.choice(LOCATIONS[state])
        lga = random.choice(LGAS[state])
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        business = random.choice(BUSINESS_NAMES) if random.random() > 0.3 else ""
        seller_type = random.choice(SELLER_TYPES)
        phone = f"080{random.randint(10000000, 99999999)}"
        email = f"{first.lower()}.{last.lower()}{random.randint(1,99)}@gmail.com"

        # Each user sells 2-4 commodities
        num_commodities = random.randint(2, 4)
        user_commodities = random.sample(COMMODITIES, num_commodities)

        reg_date = random_date(180)

        # ── Register seller ──
        c.execute("""
            INSERT INTO community_sellers
            (full_name, business_name, phone, email, location, area, lga, state,
             seller_type, commodities, date_registered, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            full_name, business, phone, email, location, location, lga, state,
            seller_type, json.dumps(user_commodities), reg_date,
            1 if random.random() > 0.4 else 0
        ))
        seller_id = c.lastrowid
        sellers_created.append(seller_id)

        # ── Add seller products + price history ──
        for comm in user_commodities:
            price_range = PRICES[comm][state]
            price = round(random.uniform(*price_range), 0)
            unit = UNITS[comm]
            platform = random.choice(["Open Market", "WhatsApp", "Phone Call"])
            today = date.today().isoformat()

            c.execute("""
                INSERT INTO seller_products
                (seller_id, commodity, price, unit, platform, quantity, availability, date_added, date_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (seller_id, comm, price, unit, platform,
                  f"{random.randint(10,500)} units", "In Stock", today, today))

            # Log to community_prices (3-8 historical entries)
            for _ in range(random.randint(3, 8)):
                hist_price = round(price * random.uniform(0.88, 1.12), 0)
                c.execute("""
                    INSERT INTO community_prices
                    (seller_id, commodity, price, unit, platform, state, date_submitted, verified_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (seller_id, comm, hist_price, unit, platform, state,
                      random_date(60), random.randint(0, 15)))

        # ── Create buyer session / user profile ──
        session_id = f"demo_user_{i+1:03d}"
        sessions_created.append(session_id)
        primary_commodity = random.choice(user_commodities)
        priority = random.choice(PRIORITIES)
        role = random.choice(ROLES)

        c.execute("""
            INSERT OR IGNORE INTO user_profiles
            (session_id, role, primary_commodity, state, bulk_frequency, priority,
             behavior_type, total_sessions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, role, primary_commodity, state,
            random.choice(BULK_FREQUENCIES), priority,
            random.choice(["price_sensitive", "quality_focused", "bulk_buyer", "opportunistic"]),
            random.randint(3, 50),
            random_date(120), random_date(10)
        ))

        # ── Behavior logs (10-25 per user) ──
        for _ in range(random.randint(10, 25)):
            comm = random.choice(user_commodities)
            c.execute("""
                INSERT INTO user_behavior_log
                (session_id, action_type, commodity, question_type, state_mentioned, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                random.choice(BEHAVIOR_ACTIONS),
                comm,
                random.choice(QUESTION_TYPES),
                state,
                random_ts(60)
            ))

        # ── Chat history (realistic buyer messages) ──
        chat_messages = [
            f"How much for {primary_commodity} today?",
            f"Abeg e don reach {random.randint(1,5)} weeks I dey buy from you, any discount?",
            f"I want to buy {random.randint(2,10)} {UNITS.get(primary_commodity, 'units')} of {primary_commodity}",
            f"Your {primary_commodity} price too high na, market dey sell am cheaper",
            f"Make I come tomorrow to collect the {primary_commodity}?",
            f"Na original {primary_commodity} you dey sell? No adulteration?",
            f"I go take {random.randint(5,20)} {UNITS.get(primary_commodity,'units')}, wetin be your best price?",
        ]
        
        target_seller_id = random.choice(sellers_created) if sellers_created else seller_id
        for msg in random.sample(chat_messages, random.randint(3, 6)):
            c.execute("""
                INSERT INTO seller_messages
                (seller_id, buyer_session_id, message, sent_by, chat_mode, is_read, saved, timestamp)
                VALUES (?, ?, ?, 'buyer', 'human', 1, 1, ?)
            """, (target_seller_id, session_id, msg, random_ts(30)))

        # ── Generated reviews ──
        for comm in random.sample(user_commodities, min(2, len(user_commodities))):
            price_range = PRICES[comm][state]
            price = round(random.uniform(*price_range), 0)
            old_price = round(price * random.uniform(0.85, 0.95), 0)
            star = random.randint(3, 5)

            templates = REVIEW_TEMPLATES.get(comm, [
                f"I buy {comm} for ₦{price:,.0f}. The quality fair, price reasonable for this market."
            ])
            review_text = random.choice(templates).format(
                price=f"₦{price:,.0f}",
                old_price=f"₦{old_price:,.0f}"
            )

            sentiment = "POSITIVE" if star >= 4 else ("NEGATIVE" if star <= 2 else "NEUTRAL")

            c.execute("""
                INSERT INTO generated_reviews
                (session_id, commodity, star_rating, review_text, sentiment,
                 price_at_review, generated_at, triggered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, comm, star, review_text, sentiment,
                price, random_ts(30), "demo_seed"
            ))

        # ── Clone training data ──
        clone_scenarios = [
            ("price_negotiation", f"Buyer offered 15% below your {primary_commodity} price", "Counter with half the discount"),
            ("bulk_deal", f"Buyer wants 20 units of {primary_commodity}", "Accept — good volume"),
            ("quality_check", f"Buyer asked for photos of {primary_commodity}", "Send photos immediately"),
            ("slow_seller", "Seller hasn't replied in 2 hours", "Send a follow-up message"),
        ]
        for scenario_type, question, answer in random.sample(clone_scenarios, 2):
            c.execute("""
                INSERT INTO clone_training
                (session_id, question, answer, scenario_type, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, question, answer, scenario_type, random_ts(20)))

        if (i + 1) % 10 == 0:
            print(f"  ✓ {i+1}/50 users seeded")

    conn.commit()
    conn.close()

    print(f"\n✅ Demo seed complete!")
    print(f"   Sellers: {len(sellers_created)}")
    print(f"   Sessions: {len(sessions_created)}")
    print(f"   Commodities: {len(COMMODITIES)}")
    print(f"\n🔑 Demo session IDs: demo_user_001 to demo_user_050")


if __name__ == "__main__":
    seed_demo()