"""
create_admin.py - Safe CLI utility to initialize the first campus administrator account
"""

import sys
import argparse
import getpass
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from database.connection import get_db, init_db_indexes

def create_or_promote_admin(full_name, email, password):
    email = email.strip().lower()
    if len(password) < 6:
        print("Error: Password must be at least 6 characters long.")
        sys.exit(1)

    db = get_db()
    init_db_indexes()

    existing = db.users.find_one({"email": email})
    if existing:
        db.users.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "role": "admin",
                    "password_hash": generate_password_hash(password),
                    "is_active": True,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        print(f"Success: Existing account for {email} has been updated with admin privileges.")
    else:
        new_admin = {
            "full_name": full_name.strip(),
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": "admin",
            "student_id": "STAFF-ADMIN",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        res = db.users.insert_one(new_admin)
        print(f"Success: Created new campus administrator: {email} (ID: {res.inserted_id})")

def main():
    parser = argparse.ArgumentParser(description="Create or promote a FindMate administrator.")
    parser.add_argument("--name", help="Admin Full Name")
    parser.add_argument("--email", help="Admin Email Address")
    parser.add_argument("--password", help="Admin Password")
    args = parser.parse_args()

    full_name = args.name
    email = args.email
    password = args.password

    if not email:
        email = input("Enter Admin Email: ").strip()
    if not full_name:
        full_name = input("Enter Admin Full Name: ").strip() or "Campus Administrator"
    if not password:
        password = getpass.getpass("Enter Admin Password (min 6 chars): ")

    create_or_promote_admin(full_name, email, password)

if __name__ == "__main__":
    main()
