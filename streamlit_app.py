import os
import sys
import io
import re
from datetime import datetime, timezone
from PIL import Image

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import streamlit as st

# 1. Sync Streamlit Cloud Secrets into os.environ
if hasattr(st, "secrets") and st.secrets:
    for key, val in st.secrets.items():
        if isinstance(val, str):
            os.environ[key] = val

# Also load from .env if running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Config
# Propagate environment variables into Config
if os.getenv("MONGO_URI"):
    Config.MONGO_URI = os.getenv("MONGO_URI")
if os.getenv("DB_NAME"):
    Config.DB_NAME = os.getenv("DB_NAME")
if os.getenv("SECRET_KEY"):
    Config.SECRET_KEY = os.getenv("SECRET_KEY")
if os.getenv("CLOUDINARY_CLOUD_NAME"):
    Config.CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
if os.getenv("CLOUDINARY_API_KEY"):
    Config.CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
if os.getenv("CLOUDINARY_API_SECRET"):
    Config.CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

from database.connection import get_db, check_db_connection
from services.item_service import ItemService, CATEGORIES, LOCATIONS
from services.auth_service import AuthService
from services.claim_service import ClaimService
from services.cloudinary_service import CloudinaryService, is_cloudinary_configured

# 2. Page Configuration
st.set_page_config(
    page_title="FindMate — Campus Lost & Found",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 3. Custom Styling
st.markdown("""
<style>
    .fm-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 1.5rem 2rem;
        border-radius: 1rem;
        color: white;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .fm-title {
        color: #F2545B !important;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    .fm-badge-lost {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .fm-badge-found {
        background-color: #dcfce7;
        color: #166534;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .fm-card {
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1rem;
        background-color: #ffffff;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
</style>
""", unsafe_allow_html=True)

# Session State for User Authentication
if "user" not in st.session_state:
    st.session_state.user = None

# Header Banner
st.markdown("""
<div class="fm-header">
    <h1 class="fm-title">🔍 FindMate</h1>
    <p style="margin: 0; color: #94a3b8; font-size: 1rem;">
        UH Mānoa Official Campus Lost & Found Registry with Cloudinary Cloud Storage
    </p>
</div>
""", unsafe_allow_html=True)

# Check DB Connection
db_connected, db_msg = check_db_connection()
if not db_connected:
    st.error("⚠️ **Database Connection Required**")
    st.markdown("""
    Streamlit Cloud is running in a remote container where **`localhost:27017` does not exist**.
    To connect your live Streamlit Cloud app to a database, you need to add your secrets in the Streamlit Cloud dashboard.
    
    ---
    ### ⚙️ Quick Setup (Takes 1-2 minutes):
    1. In the bottom-right corner of this screen, click **Manage app** (or go to your [Streamlit Cloud Dashboard](https://share.streamlit.io/)).
    2. Click the three dots `⋮` next to your app and select **Settings → Secrets**.
    3. Paste the following configuration (replace `<username>` and `<password>` with your [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) credentials):
    """)
    st.code("""
MONGO_URI = "mongodb+srv://<username>:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "findmate_db"
SECRET_KEY = "findmate-campus-secret-key-928420f871e98d748f"
CLOUDINARY_CLOUD_NAME = "itnly6gt"
CLOUDINARY_API_KEY = "148549219552935"
CLOUDINARY_API_SECRET = "rTcPhykMrFtb_MT62LoT8RCkML4"
    """, language="toml")
    st.info("💡 **Need a free MongoDB database?** Create a 100% free forever database cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas). Make sure to go to **Network Access** and click **Add IP Address → Allow from Anywhere (`0.0.0.0/0`)**.")
    st.stop()

# Quick KPI Metrics
try:
    stats = ItemService.get_summary_stats()
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Items", stats.get("total", 0))
    kpi2.metric("Active Lost", stats.get("lost_active", 0))
    kpi3.metric("Found Intake", stats.get("found_active", 0))
    kpi4.metric("Reunited & Resolved", stats.get("resolved", 0))
except Exception:
    pass

st.write("---")

# Navigation Sidebar
sidebar_options = ["📋 Browse Registry", "📝 Report Lost/Found Item", "🙋 Submit a Claim", "👤 Account & Login", "ℹ️ About & Campus Safety"]
choice = st.sidebar.radio("Navigation", sidebar_options)

# User indicator in sidebar
if st.session_state.user:
    st.sidebar.success(f"Signed in as **{st.session_state.user.get('full_name')}** ({st.session_state.user.get('role', 'student')})")
    if st.sidebar.button("Sign Out"):
        st.session_state.user = None
        st.rerun()
else:
    st.sidebar.info("Guest mode. Sign in via 'Account & Login' to submit authenticated reports.")

# -------------------------------------------------------------
# 1. BROWSE REGISTRY
# -------------------------------------------------------------
if choice == "📋 Browse Registry":
    st.subheader("Campus Registry Intake")

    # Filters
    col_search, col_cat, col_loc, col_type = st.columns([2, 1, 1, 1])
    with col_search:
        search_query = st.text_input("🔍 Search items (keywords, descriptions, locations)", "")
    with col_cat:
        category_filter = st.selectbox("Category", ["All Categories"] + CATEGORIES)
    with col_loc:
        location_filter = st.selectbox("Location", ["All Locations"] + LOCATIONS)
    with col_type:
        type_filter = st.selectbox("Report Type", ["All", "Lost", "Found"])

    filter_dict = {
        "q": search_query,
        "category": "" if category_filter == "All Categories" else category_filter,
        "building": "" if location_filter == "All Locations" else location_filter,
        "type": "" if type_filter == "All" else type_filter.lower()
    }

    try:
        results = ItemService.get_items(filters=filter_dict, page=1, per_page=18, sort_by="newest")
        items = results.get("items", [])
    except Exception as query_err:
        st.error(f"Could not load items from database: {query_err}")
        items = []
        results = {"items": [], "total": 0}

    if not items:
        st.info("No items found matching your current filter criteria.")
    else:
        st.write(f"Showing **{len(items)}** of **{results.get('total', len(items))}** reports")
        cols = st.columns(3)
        for i, item in enumerate(items):
            with cols[i % 3]:
                with st.container():
                    st.markdown("<div class='fm-card'>", unsafe_allow_html=True)
                    img_src = item.get("image_filename")
                    if img_src and str(img_src).startswith("http"):
                        st.image(img_src, use_container_width=True)
                    elif img_src:
                        # Local fallback
                        local_path = os.path.join(Config.UPLOAD_FOLDER, img_src)
                        if os.path.exists(local_path):
                            st.image(local_path, use_container_width=True)

                    type_badge = "fm-badge-lost" if item.get("report_type") == "lost" else "fm-badge-found"
                    type_label = "LOST" if item.get("report_type") == "lost" else "FOUND"
                    st.markdown(f"<span class='{type_badge}'>{type_label}</span> <span style='color: #64748b; font-size: 0.75rem; margin-left: 0.5rem;'>{item.get('report_id', '')}</span>", unsafe_allow_html=True)
                    st.markdown(f"#### {item.get('title')}")
                    st.markdown(f"📍 **{item.get('location')}**")
                    st.markdown(f"🏷️ `{item.get('category')}` &bull; 🗓️ {item.get('date_lost_or_found')}")
                    st.caption(item.get("description", ""))

                    status = item.get("resolution_status", "open")
                    if status == "resolved":
                        st.success("✅ Resolved / Reunited")
                    elif status == "claimed":
                        st.warning("⏳ Claimed (Handover in progress)")

                    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. REPORT AN ITEM
# -------------------------------------------------------------
elif choice == "📝 Report Lost/Found Item":
    st.subheader("Report an Item to the Campus Registry")
    st.caption("Photos uploaded here are automatically secured in Cloudinary.")

    report_type = st.radio("I want to report an item that is:", ["found", "lost"], format_func=lambda x: "🟢 I Found Something (Turn-In)" if x == "found" else "🔴 I Lost Something (Seeking)")

    with st.form("report_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Item Name / Title *", placeholder="e.g. Blue Hydroflask with dog stickers")
            category = st.selectbox("Item Category *", CATEGORIES)
            location = st.selectbox("Campus Location *", LOCATIONS)
        with c2:
            date_lost_or_found = st.date_input("Date Lost or Found *", max_value=datetime.now().date())
            contact_preference = st.selectbox("Preferred Return Routing", ["messaging", "desk", "direct"], format_func=lambda x: {
                "messaging": "Verified Student Messaging",
                "desk": "Campus Lost & Found Desk (Safe Station)",
                "direct": "Direct Mutual Phone Exchange"
            }.get(x, x))

        description = st.text_area("Public Description *", placeholder="Include observable colors, brands, stickers, condition...", min_chars=5)
        additional_details = st.text_input("Hidden Verification Detail (Optional)", placeholder="Serial numbers, inner engravings, or wallpaper text (hidden from public view)")

        st.write("---")
        st.markdown("##### 📷 Item Photo (Recommended)")
        photo_choice = st.radio("Choose photo input method:", ["File Upload (Gallery)", "Take a Picture with Camera"])
        photo_upload = None
        if photo_choice == "File Upload (Gallery)":
            photo_upload = st.file_uploader("Choose an image (PNG, JPG, WEBP)", type=["jpg", "png", "jpeg", "webp"])
        else:
            photo_upload = st.camera_input("Take a photo of the item")

        submitted = st.form_submit_button("Submit Item Report", use_container_width=True)

        if submitted:
            if not title.strip():
                st.error("Please enter a valid item title.")
            elif len(description.strip()) < 5:
                st.error("Please provide a description with at least 5 characters.")
            else:
                image_url = None
                if photo_upload is not None:
                    with st.spinner("Uploading image to Cloudinary storage..."):
                        try:
                            upload_res = CloudinaryService.upload_image(photo_upload.getvalue(), folder=Config.CLOUDINARY_FOLDER_ITEMS)
                            image_url = upload_res.get("secure_url")
                            st.success(f"Image uploaded to Cloudinary: {image_url}")
                        except Exception as e:
                            st.error(f"Image upload failed: {e}")

                db = get_db()
                report_id = ItemService.generate_report_id(report_type)
                contact_number = ItemService.generate_unique_contact_number()
                now = datetime.now(timezone.utc)

                creator_id = st.session_state.user.get("_id") if st.session_state.user else None

                item_doc = {
                    "title": title.strip(),
                    "category": category,
                    "report_type": report_type,
                    "location": location,
                    "date_lost_or_found": str(date_lost_or_found),
                    "description": description.strip(),
                    "additional_details": additional_details.strip(),
                    "contact_preference": contact_preference,
                    "contact_number": contact_number,
                    "image_filename": image_url,
                    "report_id": report_id,
                    "created_by": creator_id,
                    "resolution_status": "open",
                    "created_at": now,
                    "updated_at": now
                }

                try:
                    res = db.items.insert_one(item_doc)
                    st.success(f"🎉 Item registered successfully with Reference ID: **{report_id}**")
                    st.info("Your report is now live on the registry.")
                except Exception as exc:
                    st.error(f"Failed to save item to database: {exc}")

# -------------------------------------------------------------
# 3. SUBMIT A CLAIM
# -------------------------------------------------------------
elif choice == "🙋 Submit a Claim":
    st.subheader("Submit a Claim for a Found Item")
    st.caption("Provide verifying proof of ownership. Claim photos are uploaded privately to Cloudinary for owner verification.")

    db = get_db()
    found_items = list(db.items.find({"report_type": "found", "resolution_status": "open"}).sort("created_at", -1).limit(30))

    if not found_items:
        st.info("There are currently no active found items awaiting claim.")
    else:
        item_options = {str(it["_id"]): f"{it.get('report_id')} — {it.get('title')} ({it.get('location')})" for it in found_items}
        selected_item_id = st.selectbox("Select the item you are claiming:", list(item_options.keys()), format_func=lambda x: item_options[x])

        selected_item = next((it for it in found_items if str(it["_id"]) == selected_item_id), None)
        if selected_item:
            with st.expander("View Item Details", expanded=True):
                st.write(f"**Title:** {selected_item.get('title')}")
                st.write(f"**Found at:** {selected_item.get('location')} on {selected_item.get('date_lost_or_found')}")
                st.write(f"**Description:** {selected_item.get('description')}")
                if selected_item.get("image_filename") and str(selected_item.get("image_filename")).startswith("http"):
                    st.image(selected_item.get("image_filename"), width=300)

        with st.form("claim_form"):
            claimant_name = st.text_input("Your Full Name *", value=st.session_state.user.get("full_name", "") if st.session_state.user else "")
            claimant_email = st.text_input("Your Campus Email *", value=st.session_state.user.get("email", "") if st.session_state.user else "")
            claimant_phone = st.text_input("Your 10-Digit Mobile Number (starts with 6-9)", placeholder="9876543210")
            message = st.text_area("Message to Listing Owner *", placeholder="Explain when and where you lost this item...")
            verification_details = st.text_area("Proof of Ownership / Distinctive Identifiers *", placeholder="Describe unique scratches, serial numbers, screen wallpapers, or interior stickers...")

            st.markdown("##### 📷 Verification Evidence Photo *")
            st.caption("Upload a receipt, photo of you with the item, or proof matching your description.")
            claim_photo_mode = st.radio("Photo Source:", ["Upload Photo", "Take Photo with Camera"])
            claim_photo = None
            if claim_photo_mode == "Upload Photo":
                claim_photo = st.file_uploader("Upload verification evidence photo", type=["png", "jpg", "jpeg", "webp"])
            else:
                claim_photo = st.camera_input("Capture verification evidence")

            claim_submit = st.form_submit_button("Submit Claim for Verification", use_container_width=True)

            if claim_submit:
                if not message.strip() or not verification_details.strip():
                    st.error("Please fill in both the message and proof of ownership details.")
                elif not claim_photo:
                    st.error("A verification photo is required to submit a claim.")
                else:
                    with st.spinner("Uploading verification evidence to Cloudinary..."):
                        try:
                            upload_res = CloudinaryService.upload_image(claim_photo.getvalue(), folder=Config.CLOUDINARY_FOLDER_VERIFICATION)
                            cloud_photo_url = upload_res.get("secure_url")
                        except Exception as e:
                            st.error(f"Failed to upload verification photo: {e}")
                            cloud_photo_url = None

                    if cloud_photo_url:
                        from bson import ObjectId
                        claim_doc = {
                            "item_id": ObjectId(selected_item_id),
                            "requested_by": st.session_state.user.get("_id") if st.session_state.user else None,
                            "claimant_name": claimant_name,
                            "contact_email": claimant_email,
                            "claimant_phone": claimant_phone,
                            "message": message.strip(),
                            "verification_details": verification_details.strip(),
                            "verification_image_path": cloud_photo_url,
                            "status": "pending",
                            "contact_sharing_enabled": False,
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc)
                        }
                        try:
                            db.claim_requests.insert_one(claim_doc)
                            st.success("🎉 Claim submitted successfully! The listing owner has been notified to review your evidence.")
                        except Exception as e:
                            st.error(f"Database error submitting claim: {e}")

# -------------------------------------------------------------
# 4. ACCOUNT & LOGIN
# -------------------------------------------------------------
elif choice == "👤 Account & Login":
    st.subheader("Student & Staff Authentication")

    if st.session_state.user:
        st.success(f"Logged in as **{st.session_state.user.get('full_name')}** ({st.session_state.user.get('email')})")
        st.write(f"Role: `{st.session_state.user.get('role', 'student')}`")
        if st.button("Log Out"):
            st.session_state.user = None
            st.rerun()
    else:
        tab_login, tab_register = st.tabs(["Sign In", "Register New Student Account"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Campus Email (.edu)")
                password = st.text_input("Password", type="password")
                btn_login = st.form_submit_button("Sign In")
                if btn_login:
                    success, msg, user = AuthService.authenticate_user(email.strip(), password)
                    if success:
                        st.session_state.user = user
                        st.success(f"Welcome back, {user.get('full_name')}!")
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_register:
            with st.form("register_form"):
                full_name = st.text_input("Full Name")
                reg_email = st.text_input("Campus Email (e.g. name@campus.edu)")
                reg_phone = st.text_input("10-Digit Mobile Number", placeholder="9876543210")
                reg_pass = st.text_input("Password (min 6 characters)", type="password")
                reg_confirm = st.text_input("Confirm Password", type="password")
                btn_register = st.form_submit_button("Register Account")

                if btn_register:
                    success, msg, new_user = AuthService.register_user(
                        full_name=full_name.strip(),
                        email=reg_email.strip(),
                        password=reg_pass,
                        confirm_password=reg_confirm,
                        phone_number=reg_phone.strip()
                    )
                    if success:
                        st.session_state.user = new_user
                        st.success("Account registered successfully!")
                        st.rerun()
                    else:
                        st.error(msg)

# -------------------------------------------------------------
# 5. ABOUT & SAFETY
# -------------------------------------------------------------
elif choice == "ℹ️ About & Campus Safety":
    st.subheader("About FindMate & Campus Protocol")
    st.markdown("""
    **FindMate** is the official campus lost and found registry designed to streamline the recovery of misplaced personal property across university departments and hubs.
    
    ### 🛡️ Campus Safety Guidelines
    1. **Never meet strangers off-campus**: Use university designated safe exchange zones (e.g., Campus Police Station or Student Union Information Desk).
    2. **Verify ownership before handover**: Confirm unique markings, serial numbers, or locked device passcodes.
    3. **Cloud Storage Guaranteed**: All item photos and verification evidence are hosted on high-performance cloud storage powered by Cloudinary.
    """)
