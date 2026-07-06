"""
setup_mongo.py  –  CertiValidate MongoDB Setup Script
======================================================
Run once to:
  1. Verify MongoDB connectivity
  2. Create indexes on all collections
  3. Seed a default admin user (if none exists)

Usage:
    python setup_mongo.py
"""

from database import get_db, ping_db
from werkzeug.security import generate_password_hash
from datetime import datetime


ADMIN_NAME     = "Admin"
ADMIN_EMAIL    = "admin@certivalidate.com"
ADMIN_PASSWORD = "Admin@1234"   # Change in production!
ADMIN_ROLE     = "admin"


def main():
    print("=" * 60)
    print("  CertiValidate  –  MongoDB Setup")
    print("=" * 60)

    # 1. Ping
    print("\n[1] Testing MongoDB connection ...", end=" ")
    if not ping_db():
        print("FAILED [X]")
        print("\n  [X]  Cannot reach MongoDB on mongodb://localhost:27017/")
        print("  Make sure MongoDB is running:  mongod --dbpath <path>")
        return
    print("OK [OK]")

    # 2. Get DB (indexes are created inside get_db())
    db = get_db()
    print("[2] Database & indexes initialized [OK]")

    # 3. Seed admin
    existing = db.users.find_one({"email": ADMIN_EMAIL})
    if existing:
        print(f"[3] Admin user already exists ({ADMIN_EMAIL}) [OK]")
    else:
        db.users.insert_one({
            "name":               ADMIN_NAME,
            "email":              ADMIN_EMAIL,
            "password":           generate_password_hash(ADMIN_PASSWORD),
            "role":               ADMIN_ROLE,
            "is_verified":        True,
            "verification_token": None,
            "created_at":         datetime.utcnow(),
        })
        print(f"[3] Admin user created [OK]")
        print(f"      Email   : {ADMIN_EMAIL}")
        print(f"      Password: {ADMIN_PASSWORD}")
        print("      [!] Change the default password immediately!")

    print("\n[OK]  Setup complete. Run:  python app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
