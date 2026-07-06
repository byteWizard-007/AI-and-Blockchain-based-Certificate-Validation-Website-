import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
        conn.commit()
        print("Migration successful: Added is_verified and verification_token to users.")
    except sqlite3.OperationalError as e:
        print(f"Migration step skipped/failed: {e}")
        
    try:
        # We need an AI score breakdown column for storing the result for history, or we can just calculate it on the fly.
        # But wait, history requires fake vs genuine. The `certificates` table already has `ai_status` and `authenticity_score`.
        pass
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
