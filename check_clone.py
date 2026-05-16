import sqlite3

conn = sqlite3.connect('pricewise.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

session = input('Paste your session_id: ')

print('\n=== CLONE PROFILE ===')
c.execute('SELECT * FROM user_profiles WHERE session_id = ?', (session,))
p = c.fetchone()
if p: print(dict(p))
else: print('No profile found')

print('\n=== TRAINING ANSWERS ===')
c.execute('SELECT question, answer, scenario_type FROM clone_training WHERE session_id = ? ORDER BY timestamp DESC', (session,))
rows = c.fetchall()
if rows:
    for r in rows:
        print(f'  [{r["scenario_type"]}] A: {r["answer"]}')
else: print('No training yet')

print('\n=== STYLE EXAMPLES ===')
c.execute('SELECT example_message, context FROM clone_style_examples WHERE session_id = ?', (session,))
rows = c.fetchall()
if rows:
    for r in rows:
        print(f'  [{r["context"]}] {r["example_message"]}')
else: print('No style examples yet')

print('\n=== CHAT HISTORY ===')
c.execute('SELECT COUNT(*) as cnt FROM seller_messages WHERE buyer_session_id = ? AND sent_by = "buyer"', (session,))
cnt = c.fetchone()["cnt"]
print(f'  {cnt} buyer messages learned from')

print('\n=== CLONE STAGE ===')
c.execute('SELECT COUNT(*) as cnt FROM clone_training WHERE session_id = ?', (session,))
t = c.fetchone()["cnt"]
c.execute('SELECT COUNT(*) as cnt FROM clone_style_examples WHERE session_id = ?', (session,))
e = c.fetchone()["cnt"]
total = cnt + t + e
stage = "BEGINNER" if total < 10 else "LEARNING" if total < 30 else "TRAINED"
print(f'  Stage: {stage} | Total signals: {total}')

conn.close()