import sqlite3

def init_db():
    
    # it creates the database and connects it meaning now connection is open and we can execute 
    conn = sqlite3.connect('pricewise.db')
    
    # conn.cursor is like calling a pen to write out what to store in the database 
    c = conn.cursor()
    
    # this means run or perform the tasks in the brackets
    # CREATE TABLE IF NOT EXISTS means if the table doesn't exist then create it, if it does exist then do nothing 
    # products is the name of the table, id is the primary key and it will auto increment every time we add a new product
    # name is a text field that cannot be empty
    # url is a text field that is optional
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT
        )
    ''')
    
    # foreign key is a field in one table that refers to the primary key in another table, in this case product_id in price_history refers to id in products
    # references is used to link the two tables together, so that we can easily query the price history for a specific 
    # the comment shows only the id available in the price_history and it must match an id in the products table
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
    

