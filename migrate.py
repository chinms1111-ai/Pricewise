import sqlite3

conn = sqlite3.connect("pricewise.db")
c = conn.cursor()

# Drop both old tables with wrong schemas
c.execute("DROP TABLE IF EXISTS community_prices")
c.execute("DROP TABLE IF EXISTS community_sellers")

# Recreate community_sellers with correct schema
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

# Recreate community_prices with correct schema
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
print("Done. Both tables recreated with correct schema.")