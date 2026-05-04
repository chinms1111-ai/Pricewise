import sqlite3

def init_db():
    conn = sqlite3.connect('pricewise.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            date TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database ready.")
    
init_db()
    

