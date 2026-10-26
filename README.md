# BloodLink — Blood Donation & Emergency Finder

BloodLink is a web-based emergency blood donation matching and community campaign management platform. It bridges the critical time gap during medical emergencies by connecting voluntary blood donors directly with patients and hospitals in need, driven by a biological compatibility matching and scoring algorithm.

---

## 1. Project Purpose & Highlights

- **Emergency Request Broadcasting:** Patients and hospitals can broadcast urgent blood requirements with units needed, urgency levels (`CRITICAL`, `HIGH`, `NORMAL`, `LOW`), and hospital admission details.
- **Algorithm-Driven Compatible Match Finder:** Automatically maps universal and specific red blood cell compatibility rules (ABO and Rh factor) combined with geographic proximity to rank eligible donors.
- **Privacy-Preserving Contact Reveal:** Protects donor privacy by keeping telephone numbers masked during public searches. Donor contact information is only revealed to a recipient after the donor explicitly grants consent and the recipient accepts the donation offer.
- **Community Blood Donation Campaigns:** Admin-managed blood collection drives with calendar filtering (`UPCOMING`, `ONGOING`, `COMPLETED`, `CANCELLED`), venue details, target collection units, and dynamic public feeds for donors and recipients.
- **Enterprise-Grade Access Control & Reliability:** Role-based authorization (`ADMIN`, `DONOR`, `RECIPIENT`), object-level ownership checks (preventing IDOR), CSRF same-origin defense-in-depth, parameterized SQL queries, and resource cleanup guarantees.

---

## 2. Technology Stack

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Backend Web Framework** | Python 3.10+ / Flask 3.1.3 | RESTful JSON endpoints, session management, route decorators |
| **Database** | MySQL 8.0+ / `mysql-connector-python` 26.7.0 | Relational database (7 tables), referential foreign keys |
| **Security & Auth** | Werkzeug 3.1.8 / PBKDF2:SHA256 | Password hashing, HTTPOnly session cookies, SameSite lax cookies |
| **Frontend** | Vanilla HTML5, CSS3, ES6+ JavaScript | Modern SPA-style dashboards, accessible modals, dynamic DOM rendering |
| **Data Structures & Algorithms** | Python Hash Tables, Bubble Sort | $O(1)$ medical compatibility lookups, multi-criteria scoring, stable sorting |

---

## 3. Directory Structure

```
BloodLink/
├── app.py                   # Main Flask application and REST API routes (43 endpoints)
├── database.py              # MySQL connection factory with dynamic .env configuration
├── matching.py              # Blood compatibility matrix, scoring, and sorting algorithms
├── migrate_db.py            # Legacy database migration script (preserved for backward compatibility)
├── schema.sql               # Complete standalone clean database schema & reference data
├── requirements.txt         # Pinned Python package dependencies
├── .env.example             # Safe template for environment configuration (placeholders only)
├── .gitignore               # Exclusion rules for secrets, .env, backups, and local artifacts
├── templates/               # Server-rendered Jinja2 HTML templates
│   ├── index.html           # Landing page with public hero, live stats, and features
│   ├── login.html           # User authentication login interface
│   ├── signup.html          # Role-based user registration interface
│   ├── donor_dashboard.html # Donor management, availability toggle, offers, and campaigns
│   ├── recipient_dashboard.html # Emergency broadcasts, compatible search, offer acceptance
│   └── admin_dashboard.html # Analytics, user management, requests, and campaign CRUD
├── static/                  # Static CSS styles and client-side JavaScript assets
├── tests/                   # Automated unit and integration test suite (332 passing tests)
└── backups/                 # Local timestamped code and database snapshots (git-ignored)
```

---

## 4. Prerequisites

- **Python:** Version 3.10 or higher (tested on Python 3.10 through 3.14).
- **MySQL Server:** Version 8.0 or higher running locally or accessible over the network.
- **Git:** Version 2.20 or higher.
- **Shell / Terminal:** PowerShell (Windows) or Bash / Zsh (Linux / macOS).

---

## 5. Quickstart & Installation

### Step 1: Clone or Navigate to the Repository
```bash
git clone https://github.com/<your-username>/BloodLink.git
cd BloodLink
```

### Step 2: Set Up Virtual Environment
```bash
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy the template configuration file to `.env`:
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```
Open `.env` in an editor and set your local MySQL credentials and session secret keys:
```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_actual_mysql_password
DB_NAME=blood_donation
SECRET_KEY=your_persistent_64_char_hex_secret_key
FLASK_SECRET_KEY=your_persistent_64_char_hex_secret_key
SESSION_COOKIE_SECURE=False
```
*(Tip: Generate a strong secret key in your terminal via: `python -c "import secrets; print(secrets.token_hex(32))"`)*

### Step 5: Initialize the MySQL Database
Ensure your MySQL service is running. Import `schema.sql` to provision the database (`blood_donation`), all 7 tables, constraints, and demonstration healthcare facilities:

```bash
# Windows (PowerShell or CMD) — Recommended universal command:
mysql -u root -p -e "source schema.sql"

# Windows (Command Prompt alternative):
mysql -u root -p < schema.sql

# Windows (PowerShell raw piping alternative):
Get-Content -Raw schema.sql | mysql -u root -p

# Linux / macOS / Git Bash:
mysql -u root -p < schema.sql
```
*(Note: `schema.sql` includes `CREATE DATABASE IF NOT EXISTS blood_donation;` and `USE blood_donation;`, so you do not need to create or select the database separately).*

> **Note on Hospital Reference Data & Migrations:**
> - `schema.sql` seeds 5 sample healthcare facilities with dummy contact numbers strictly for local development and UI dropdown population. These do not represent real institutions and can be customized as needed.
> - `schema.sql` provisions the complete, up-to-date schema. No additional migration is required for a fresh install. `migrate_db.py` is preserved strictly for backwards compatibility to upgrade older legacy databases.

### Step 6: (Optional) Promote an Administrator Account
Public signup creates `DONOR` or `RECIPIENT` accounts. To create an `ADMIN` account:
1. Register a new user at `http://localhost:5000/signup`.
2. Promote the account to `ADMIN` in MySQL:
   ```sql
   USE blood_donation;
   UPDATE users SET role = 'ADMIN' WHERE email = 'your_admin_email@example.com';
   ```

### Step 7: Run the Application
```bash
python app.py
```
Access the application in your web browser at:
`http://localhost:5000`

---

## 6. Running the Automated Test Suite

BloodLink includes a test suite covering authentication, RBAC authorization, object ownership, emergency offer workflows, campaign management, CSRF validation, and algorithm edge cases:

```bash
# Run all tests across the suite
python -m unittest discover tests

# Run targeted Stage 1 & Stage 2 security and reliability suites
python -m unittest tests/test_stage1_security_reliability.py
python -m unittest tests/test_stage2_security_functional.py
```
**Current Baseline:** **332 passing tests** (0 failures, 0 errors, 0 skipped).

---

## 7. Security & Privacy Architecture

1. **Defense-in-Depth CSRF Protection:** State-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`) are verified against browser `Origin`, `Referer`, and W3C `Sec-Fetch-Site` metadata. Cross-site mutations or malformed headers are rejected with HTTP 403.
2. **Strict Role-Based Access Control (RBAC):** Custom decorators (`@login_required`, `@roles_required`) prevent privilege escalation. Role checks on donation offers are enforced before querying the database, ensuring accounts with the `RECIPIENT` role cannot offer donations even if a linked profile row exists.
3. **Inversion of Direct Object References (IDOR):** Endpoints modifying emergency request statuses or responding to donation offers verify that the authenticated `session['user_id']` owns the underlying resource.
4. **SQL Injection Immunity:** All dynamic database operations use `%s` parameterization. No dynamic string concatenation or raw SQL interpolation is used.
5. **Donor Contact Privacy:** Telephone numbers are masked in all public and search queries. Recipient dashboards only display donor contact numbers after an offer is transitioned to `ACCEPTED` and the donor has recorded explicit consent.
6. **Connection Reassurance:** All database access routes utilize `try ... finally` blocks to guarantee `cursor.close()` and `connection.close()` execution under all conditions.

---

## 8. Academic & Faculty Explanation Guide (DSA)

When explaining the matching engine to university faculty or examiners, reference the following architectural principles:

- **Medical Compatibility Matrix (`matching.py`):**
  Uses an $O(1)$ constant-time dictionary lookup mapping donor red blood cell types to acceptable recipient types based on international immunohematology guidelines.
  - Universal Red Cell Donor: `O-` (compatible with all 8 groups).
  - Universal Red Cell Recipient: `AB+` (accepts all 8 groups).
- **Composite Scoring Function:**
  - Exact blood group match: $+60$ points.
  - Compatible blood group match: $+40$ points.
  - Geographic location match (case-normalized and whitespace-trimmed): $+20$ points.
  - Maximum score: $80$ points.
- **Bubble Sort with Early-Termination Optimization (`bubble_sort`):**
  - Sorts candidate donors in descending order of matching score.
  - Includes a `swapped` boolean sentinel flag. If an array of candidate donors is already sorted, the algorithm terminates after one pass ($O(N)$ best case).
  - Preserves stability: Donors with identical scores maintain their original registration order.

---

## 9. Version Control & Privacy Safeguards

The repository is configured to be clean and safe for version control (GitHub):
- `.env` and `.env.*` are excluded by `.gitignore`.
- Database dump files (`*.sql`, `*.dump`) and local backups (`backups/`) are strictly git-ignored.
- No live passwords, API secrets, session tokens, or personal phone numbers are committed to Git.
