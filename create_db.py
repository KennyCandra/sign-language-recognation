import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    email TEXT,
    password TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS quiz_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_answers INTEGER NOT NULL,
    wrong_answers INTEGER NOT NULL,
    score_percent REAL NOT NULL,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS learning_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    is_favorite INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
""")

# Migration safety for old databases.
cursor.execute("PRAGMA table_info(learning_history)")
cols = [r[1] for r in cursor.fetchall()]
if 'is_favorite' not in cols:
    cursor.execute("ALTER TABLE learning_history ADD COLUMN is_favorite INTEGER DEFAULT 0")

conn.commit()
conn.close()

print("Database schema created/updated")
