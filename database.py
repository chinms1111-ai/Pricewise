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
 
    # Price history table — platform column included
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
 
    # Community sellers table — correct schema
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
 
    # Community prices table — correct schema
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
 
    # State prices table — for arbitrage detection
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
 
    conn.commit()
    conn.close()
    print("Database ready.")
 
 
def migrate_community_tables():
    """
    Drops and recreates community_sellers and community_prices
    with the correct schema. Safe to run on Render — only touches
    these two tables, all other data is preserved.
    """
    conn = sqlite3.connect('pricewise.db')
    c = conn.cursor()
 
    c.execute("DROP TABLE IF EXISTS community_prices")
    c.execute("DROP TABLE IF EXISTS community_sellers")
 
    c.execute('''
        CREATE TABLE community_sellers (
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
 
    c.execute('''
        CREATE TABLE community_prices (
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
 
    conn.commit()
    conn.close()
    print("Migration done. community_sellers and community_prices recreated.")
 
 
init_db()
 