# FindMate — Campus Lost & Found Portal

FindMate is a campus lost and found web application designed for college students, faculty, and campus security staff to report lost items, register found belongings, securely verify ownership, and coordinate safe campus handovers.

Built with **Python**, **Flask**, **PyMongo**, and **MongoDB Community Server**, FindMate closely follows the Google Stitch collegiate design language.

---

## 1. Key Features

- **Google Stitch Collegiate UI**: Faithful recreation of the FindMate reference designs, including forest green collegiate palette, responsive navbar with active link indicator, custom pill badges, and interactive cards.
- **Real MongoDB Persistence**: Complete CRUD operations stored in `findmate_db` with PyMongo.
- **Student Authentication & Authorization**:
  - Secure registration and login with Werkzeug password hashing.
  - Role-based access control (`student` vs `admin`).
  - Protection against unauthorized role escalation on public signup.
  - Session-based CSRF protection on all state-changing operations.
- **Search, Filtering, and Pagination**:
  - Full-text search and case-insensitive regex filtering across titles, descriptions, and campus locations.
  - Instant filters by report type (`Lost`, `Found`, `Resolved`), category, building/hub, and term.
  - URL-preserved query parameters and pagination controls.
- **Safe Claim Verification Workflow**:
  - Students submit proof of ownership and confidential verification details.
  - Duplication checks prevent spam claims.
  - Only listing owners or campus administrators can review, approve, or reject claims.
  - Approving a claim automatically marks the item as `claimed` and resolves conflicting pending requests.
- **Student Dashboard**:
  - Personal overview metrics (My Total Reports, Active Lost Alerts, Found Logged, Reunited).
  - Tabbed interface to manage reported items, review claims received from other students, and track submitted claim requests.
- **Campus Admin Console**:
  - System-wide statistics and MongoDB aggregation pipelines.
  - Item moderation (view, edit, toggle status, delete).
  - Claims audit log with direct approval/rejection.
  - Student account management with safeguards against self-deactivation.
- **Secure File Uploads**:
  - Validates file extensions and authenticates image content using Pillow (`PIL.Image`).
  - Filenames randomized with UUIDs to prevent directory traversal and overwrite attacks.

---

## 2. Technology Stack

- **Backend**: Python 3.10+ (Tested on Python 3.14)
- **Web Framework**: Flask 3.1+
- **Database**: MongoDB Community Server (`mongodb://localhost:27017/`)
- **Database Driver**: PyMongo 4.19+
- **Security & Validation**: Werkzeug, email-validator, Pillow
- **Frontend**: HTML5, Vanilla CSS3 (Custom FindMate Design System), Bootstrap 5.3 (grid/utilities), Jinja2 templates

---

## 3. MongoDB Database Architecture

Database name: `findmate_db`

### Collections

#### A. `users`
- `_id`: ObjectId
- `full_name`: string (2-80 chars)
- `email`: string (unique, normalized lowercase)
- `password_hash`: string (Werkzeug scrypt/pbkdf2 hash)
- `role`: string (`student` or `admin`)
- `student_id`: string (optional, e.g. `UH-104928`)
- `is_active`: boolean
- `created_at`: UTC datetime
- `updated_at`: UTC datetime

**Indexes:**
- `email` (unique index: `uniq_user_email`)
- `role` (index: `idx_user_role`)

#### B. `items`
- `_id`: ObjectId
- `title`: string
- `category`: string (e.g., Electronics, Water Bottles, Apparel & Gear, etc.)
- `report_type`: string (`lost` or `found`)
- `location`: string (e.g., Hamilton Library, Campus Center, Gilmore Hall)
- `date_lost_or_found`: string (`YYYY-MM-DD`)
- `academic_term`: string (`Fall 2025`, `Spring 2025`)
- `description`: string
- `additional_details`: string (hidden verification key / unique identifier)
- `contact_preference`: string (`direct` or `desk`)
- `image_filename`: string
- `report_id`: string (e.g., `#LF-2025-1047`, `#FD-2025-1044`)
- `created_by`: ObjectId reference to `users`
- `resolution_status`: string (`open`, `claimed`, `resolved`)
- `created_at`: UTC datetime
- `updated_at`: UTC datetime

**Indexes:**
- Compound index on `(report_type, resolution_status)`
- Index on `category`, `location`, `created_at`, `created_by`
- Text index on `title`, `description`, `location`, `additional_details`

#### C. `claim_requests`
- `_id`: ObjectId
- `item_id`: ObjectId reference to `items`
- `requested_by`: ObjectId reference to `users`
- `message`: string
- `verification_details`: string
- `contact_email`: string
- `status`: string (`pending`, `approved`, `rejected`)
- `reviewer_notes`: string
- `created_at`: UTC datetime
- `updated_at`: UTC datetime

**Indexes:**
- Compound index on `(item_id, requested_by)`
- Index on `item_id`, `requested_by`, `status`, `created_at`

---

## 4. Search & Filtering Strategy

Search leverages a dual approach:
1. **Compound Multi-Field Regex & Text Search**: Queries safely escape user input and construct MongoDB queries matching `title`, `description`, and `location` case-insensitively using `$or` operators.
2. **MongoDB Text Indexes**: Text indexes are initialized on `(title, description, location, additional_details)` to support natural language queries.
3. **Database-Level Filtering**: Queries use `$in`, `$gte`, `$lte`, and `$regex` directly in MongoDB rather than filtering in Python memory.
4. **Pagination**: Managed via `.skip()` and `.limit()` on sorted MongoDB cursors.

---

## 5. Local Setup & Running Instructions

### Step 1: Start MongoDB Community Server
Ensure your local MongoDB service is running on `localhost:27017`:
```bash
# Verify MongoDB port 27017 is listening:
# On Windows, MongoDB runs as a background service: "MongoDB Server (MongoDB)"
```

### Step 2: Create and Activate Virtual Environment
```bash
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```
Default configuration values:
- `MONGO_URI=mongodb://localhost:27017/`
- `DB_NAME=findmate_db`
- `SECRET_KEY=your-secure-secret-key`
- `PORT=5000`
- `HOST=127.0.0.1`

### Step 5: Clean State & Admin Account Creation (Default)
FindMate starts in a **clean, brand-new state** with no automatically inserted records. All collections (`items`, `claim_requests`, and `users`) are empty upon first installation.

To create the first campus administrator safely via the secure CLI tool:
```bash
python create_admin.py --name "Campus Administrator" --email "admin@findmate.campus.edu" --password "your_secure_password"
```
Or run interactively to be prompted for credentials:
```bash
python create_admin.py
```

### Step 6: Database Reset and Demo Data Utilities
- **Reset Database to Clean State**:
  To reset the database back to a clean empty state with safe confirmation:
  ```bash
  python reset_db.py
  ```
  *(Requires typing `YES` or passing `--confirm-all` to prevent accidental deletion).*

- **Remove Only Demo Records**:
  If you have created real reports/accounts and only want to clean out legacy seeded documents:
  ```bash
  python clean_demo_data.py
  ```

- **Optional Demo Seeding (For Demonstration Only)**:
  If demo listings are ever needed for a presentation, run:
  ```bash
  python seed_data.py
  ```
  *Note: Seeding is strictly optional and is NEVER executed automatically during application startup.*

### Step 7: Run Automated Tests
Execute the unit and integration test suite:
```bash
python -m unittest tests/test_findmate.py
```
*Note: The test suite runs against an isolated test database `findmate_test_db` so development data in `findmate_db` is never modified or erased.*

### Step 8: Start the Web Application
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000/
```

---

## 6. Project Structure

```
FindMate/
├── app.py                     # Application factory, error handlers, Jinja filters
├── config.py                  # Environment configuration & session security
├── requirements.txt           # Python package dependencies
├── .env.example               # Example environment variables template
├── .env                       # Local environment settings
├── seed_data.py               # Database seeder matching Stitch designs (optional)
├── clean_demo_data.py         # Removes demo accounts and items while preserving real data
├── reset_db.py                # Safe interactive database reset utility
├── create_admin.py            # CLI tool for safe administrator setup
├── README.md                  # Complete documentation
├── database/
│   ├── __init__.py
│   └── connection.py          # PyMongo connection & index initialization
├── routes/
│   ├── __init__.py
│   ├── auth_routes.py         # Login, registration, logout, forgot password
│   ├── item_routes.py         # Home, browse, details, report, edit, delete
│   ├── claim_routes.py        # Claim submission and review routes
│   ├── dashboard_routes.py    # Student dashboard portal
│   └── admin_routes.py        # Protected administrator console
├── services/
│   ├── __init__.py
│   ├── auth_service.py        # Authentication & CSRF logic
│   ├── item_service.py        # Item CRUD, queries, search, file uploads
│   └── claim_service.py       # Claim validation & approval workflow
├── templates/
│   ├── base.html              # Base collegiate template with navbar & footer
│   ├── home.html              # Home page with campus snapshots & stats
│   ├── browse_items.html      # Filterable registry listing with cards & pagination
│   ├── item_details.html      # Listing details, gallery, verification modal
│   ├── report_item.html       # Report lost/found item with photo dropzone
│   ├── edit_item.html         # Report modification form
│   ├── login.html             # Sign in with student or admin credentials
│   ├── register.html          # Student registration
│   ├── forgot_password.html   # Password recovery instructions
│   ├── student_dashboard.html # Student reports and claim tracking
│   ├── claim_requests.html    # Claim requests view
│   ├── admin_dashboard.html   # Admin console with KPI metrics & moderation
│   ├── faq.html               # Frequently asked questions & safety rules
│   ├── 404.html               # 404 Not Found error page
│   └── 500.html               # 500 Server Error page
├── tests/
│   └── test_findmate.py       # Automated test suite (9 passing tests)
└── static/
    ├── css/
    │   ├── style.css          # FindMate custom collegiate stylesheet
    │   └── responsive.css     # Tablet & mobile responsive adjustments
    ├── js/
    │   ├── main.js            # Image preview, drag & drop, type toggles
    │   └── filters.js         # Search/filter submissions and gallery switcher
    ├── images/                # Campus hubs, avatars, and UI assets
    └── uploads/               # User uploaded item photos
```

---

## 7. Security & Privacy Implementations

1. **Password Security**: Passwords are hashed with Werkzeug's secure hash algorithm; plaintext passwords are never stored or logged.
2. **Session Security**: Session cookies use `HttpOnly` and `SameSite=Lax` configurations.
3. **Role Escalation Safeguard**: Public signups are explicitly forced to the `student` role. Admin accounts can only be provisioned via `create_admin.py` or by an existing admin in the admin console.
4. **CSRF Protection**: All POST/PUT/DELETE forms include cryptographic CSRF tokens verified before processing.
5. **Image File Security**: User uploads are verified using Pillow to ensure valid image data, extensions are restricted, file sizes are limited to 5MB, and filenames are randomized with UUIDs.
6. **Authorization Checks**: Every edit, deletion, and claim review verifies that the requesting user is either the listing creator or an authenticated administrator.
