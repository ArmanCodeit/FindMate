"""
reset_db.py - Safe, explicit database reset utility for FindMate.
WARNING: This is a destructive operation and requires explicit confirmation.
"""

import sys
import argparse
from database.connection import get_db, init_db_indexes

def reset_database(force=False):
    if not force:
        print("=" * 60)
        print("WARNING: This command will permanently delete ALL documents")
        print("from findmate_db (users, items, claim_requests).")
        print("=" * 60)
        confirm = input("Type 'YES' to confirm total database wipe: ").strip()
        if confirm != "YES":
            print("Operation aborted. No changes made.")
            sys.exit(0)

    db = get_db()
    users_count = db.users.count_documents({})
    items_count = db.items.count_documents({})
    claims_count = db.claim_requests.count_documents({})

    db.users.delete_many({})
    db.items.delete_many({})
    db.claim_requests.delete_many({})

    # Safely re-initialize indexes
    init_db_indexes()

    print(f"Database reset complete:")
    print(f" - Removed {users_count} user(s)")
    print(f" - Removed {items_count} item(s)")
    print(f" - Removed {claims_count} claim request(s)")
    print("Database findmate_db is now completely empty and indexed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset findmate_db to a completely empty state.")
    parser.add_argument("--confirm-all", action="store_true", help="Bypass interactive confirmation prompt.")
    args = parser.parse_args()

    reset_database(force=args.confirm_all)
