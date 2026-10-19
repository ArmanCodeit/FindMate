"""
clean_demo_data.py - Safely removes only the demo seed records from findmate_db,
preserving real user accounts and real listings.
"""

from database.connection import get_db

def purge_demo_data():
    db = get_db()
    
    demo_emails = [
        "riya.sharma@hawaii.edu",
        "alex.m@hawaii.edu",
        "admin@findmate.campus.edu"
    ]
    demo_report_ids = [
        "#FD-2025-1044",
        "#LF-2025-1047",
        "#FD-2025-1048",
        "#LF-2025-1049",
        "#FD-2025-1050",
        "#LF-2025-1051",
        "#FD-2025-1052",
        "#FD-2025-1053",
        "#FD-2025-1054",
        "#FD-2025-1055"
    ]
    
    # 1. Find demo item ids
    demo_items = list(db.items.find({"report_id": {"$in": demo_report_ids}}, {"_id": 1}))
    demo_item_ids = [it["_id"] for it in demo_items]
    
    # 2. Delete demo claims
    claims_del = db.claim_requests.delete_many({"item_id": {"$in": demo_item_ids}})
    
    # 3. Delete demo items
    items_del = db.items.delete_many({"report_id": {"$in": demo_report_ids}})
    
    # 4. Delete demo users
    users_del = db.users.delete_many({"email": {"$in": demo_emails}})
    
    print(f"Purge complete:")
    print(f" - Deleted {users_del.deleted_count} demo user account(s)")
    print(f" - Deleted {items_del.deleted_count} demo item listing(s)")
    print(f" - Deleted {claims_del.deleted_count} demo claim request(s)")
    
    remaining_users = list(db.users.find({}, {"email": 1, "full_name": 1, "role": 1}))
    remaining_items = list(db.items.find({}, {"title": 1, "report_id": 1, "report_type": 1}))
    remaining_claims = db.claim_requests.count_documents({})
    
    print("\nPreserved Real Database State:")
    print(f" - Users ({len(remaining_users)}):", remaining_users)
    print(f" - Items ({len(remaining_items)}):", remaining_items)
    print(f" - Claims ({remaining_claims}):", remaining_claims)

if __name__ == "__main__":
    purge_demo_data()
