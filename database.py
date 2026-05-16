import sqlite3
 
def init_db():
    conn = sqlite3.connect('pricewise.db')
    c = conn.cursor()
 
    # Products table
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT
        )
    ''')
 
    # Price history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            platform TEXT,
            date TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
 
    # User sessions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'consumer',
            commodities TEXT DEFAULT '[]',
            questions TEXT DEFAULT '[]',
            last_seen TEXT
        )
    ''')
 
    # Community sellers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS community_sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            business_name TEXT,
            phone TEXT,
            location TEXT NOT NULL,
            area TEXT NOT NULL,
            lga TEXT NOT NULL,
            state TEXT NOT NULL,
            seller_type TEXT NOT NULL,
            commodities TEXT NOT NULL,
            date_registered TEXT,
            verified INTEGER DEFAULT 0
        )
    ''')
 
    # Community prices table — kept for price history & agent
    c.execute('''
        CREATE TABLE IF NOT EXISTS community_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            platform TEXT DEFAULT 'Open Market',
            state TEXT NOT NULL,
            date_submitted TEXT NOT NULL,
            verified_count INTEGER DEFAULT 0,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')

    # ── NEW: Seller products — live listings managed by seller ──
    # One seller can have many products. Seller edits these themselves.
    c.execute('''
        CREATE TABLE IF NOT EXISTS seller_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            platform TEXT DEFAULT 'Open Market',
            quantity TEXT DEFAULT '',
            availability TEXT DEFAULT 'In Stock',
            date_added TEXT NOT NULL,
            date_updated TEXT NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')
 
    # User profiles
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            role TEXT,
            primary_commodity TEXT,
            state TEXT,
            bulk_frequency TEXT,
            priority TEXT,
            behavior_type TEXT,
            total_sessions INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
 
    # User behavior log
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_behavior_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            commodity TEXT,
            question_type TEXT,
            state_mentioned TEXT,
            timestamp TEXT NOT NULL
        )
    ''')
 
    # Generated reviews
    c.execute('''
        CREATE TABLE IF NOT EXISTS generated_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            commodity TEXT NOT NULL,
            star_rating INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            sentiment TEXT,
            price_at_review REAL,
            generated_at TEXT NOT NULL,
            triggered_by TEXT DEFAULT 'manual'
        )
    ''')
 
    # State prices table
    c.execute('''
        CREATE TABLE IF NOT EXISTS state_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            price REAL NOT NULL,
            platform TEXT,
            date TEXT,
            source TEXT DEFAULT 'seeded',
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    # Comments on seller profiles
    c.execute('''
        CREATE TABLE IF NOT EXISTS commodity_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            session_id TEXT NOT NULL,
            comment TEXT NOT NULL,
            star_rating INTEGER DEFAULT 0,
            sentiment TEXT DEFAULT 'NEUTRAL',
            sent_by TEXT DEFAULT 'user',
            timestamp TEXT NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')
    
    # Seller messages (private chat)
    c.execute('''
        CREATE TABLE IF NOT EXISTS seller_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            buyer_session_id TEXT NOT NULL,
            message TEXT NOT NULL,
            sent_by TEXT DEFAULT 'buyer',
            chat_mode TEXT DEFAULT 'human',
            is_read INTEGER DEFAULT 0,
            saved INTEGER DEFAULT 1,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')
    
    
    
    # Clone training questions answered by user
    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_training (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            scenario_type TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    # Clone daily questions queue
    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            scenario_type TEXT NOT NULL,
            options TEXT NOT NULL,
            answered INTEGER DEFAULT 0,
            answer TEXT DEFAULT NULL,
            date_shown TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    # Clone chat style examples written by user
    c.execute('''
        CREATE TABLE IF NOT EXISTS clone_style_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            example_message TEXT NOT NULL,
            context TEXT DEFAULT 'general',
            timestamp TEXT NOT NULL
        )
    ''')
 
    conn.commit()
    conn.close()
    print("Database ready.")
 
 
def migrate_community_tables():
    """
    Safe migration — only touches community tables.
    Adds seller_products if it doesn't exist.
    """
    conn = sqlite3.connect('pricewise.db')
    c = conn.cursor()

    # Add seller_products if missing (safe on existing DB)
    c.execute('''
        CREATE TABLE IF NOT EXISTS seller_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            platform TEXT DEFAULT 'Open Market',
            quantity TEXT DEFAULT '',
            availability TEXT DEFAULT 'In Stock',
            date_added TEXT NOT NULL,
            date_updated TEXT NOT NULL,
            FOREIGN KEY (seller_id) REFERENCES community_sellers (id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Migration done. seller_products table ready.")
 
 
init_db()