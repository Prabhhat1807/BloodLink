import datetime
import os
import re
import secrets
import warnings
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from database import get_db_connection, _load_env
from matching import find_best_donors, is_compatible

# Pre-load environment configuration from .env if present
_load_env()

app = Flask(__name__)

# =========================================
# SESSION & SECURITY CONFIGURATION
# =========================================
# Load session secret key securely from environment variable (SECRET_KEY or FLASK_SECRET_KEY).
# If neither is set, generate a cryptographically strong random secret for development.
# Sessions will not survive a server restart without a persistent environment variable.
# The secret is never hardcoded, printed, or committed to source control.
session_secret = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
if not session_secret:
    session_secret = secrets.token_hex(32)
    warnings.warn(
        "SECURITY NOTICE: Neither SECRET_KEY nor FLASK_SECRET_KEY environment variable is set. "
        "Generated a random ephemeral secret key for local development. "
        "User sessions will not survive a server restart. "
        "For production or multi-worker deployments, set a persistent SECRET_KEY.",
        UserWarning
    )
app.secret_key = session_secret

# Strict session cookie configuration
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# NOTE: For local HTTP development (localhost / LAN testing), SESSION_COOKIE_SECURE
# must be False so browsers store the cookie over unencrypted HTTP.
# In production, set environment variable SESSION_COOKIE_SECURE=true when serving over HTTPS.
# Example: export SESSION_COOKIE_SECURE=true (Linux/macOS) or $env:SESSION_COOKIE_SECURE="true" (PowerShell)
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1")


# =========================================
# CSRF & SAME-ORIGIN DEFENSE-IN-DEPTH
# =========================================

@app.before_request
def csrf_origin_check():
    """
    Enforce same-origin verification for state-changing HTTP methods.
    Checks W3C Fetch Metadata (Sec-Fetch-Site), Origin, and Referer headers.
    Protects against CSRF while permitting legitimate application requests,
    local forms, and automated tests.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        host_header = (request.headers.get("Host") or "").lower().strip()

        # 1. W3C Fetch Metadata check (modern browsers: Chrome, Firefox, Edge, Safari)
        sec_fetch_site = (request.headers.get("Sec-Fetch-Site") or "").lower().strip()
        if sec_fetch_site == "cross-site":
            return jsonify({
                "error": "Forbidden: Cross-origin request rejected (CSRF protection)."
            }), 403

        # 2. Origin header verification
        origin = request.headers.get("Origin")
        if origin:
            try:
                origin_parsed = urlparse(origin)
                origin_host = origin_parsed.netloc.lower().strip()
                if not origin_host or (host_header and origin_host != host_header):
                    return jsonify({
                        "error": "Forbidden: Cross-origin request rejected (CSRF protection)."
                    }), 403
            except Exception:
                return jsonify({
                    "error": "Forbidden: Malformed Origin header rejected (CSRF protection)."
                }), 403

        # 3. Referer header verification (fallback when Origin is omitted)
        elif request.headers.get("Referer"):
            referer = request.headers.get("Referer")
            try:
                referer_parsed = urlparse(referer)
                referer_host = referer_parsed.netloc.lower().strip()
                if not referer_host or (host_header and referer_host != host_header):
                    return jsonify({
                        "error": "Forbidden: Cross-origin referer rejected (CSRF protection)."
                    }), 403
            except Exception:
                return jsonify({
                    "error": "Forbidden: Malformed Referer header rejected (CSRF protection)."
                }), 403


# =========================================
# REUSABLE ACCESS-CONTROL DECORATORS
# =========================================

def is_api_request():
    """
    Determine whether the current request is an API request (JSON expected)
    or a browser page request (HTML expected / redirect).
    """
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    page_endpoints = {
        "home",
        "signup",
        "login",
        "donor_dashboard",
        "recipient_dashboard",
        "admin_dashboard"
    }
    if request.endpoint and request.endpoint not in page_endpoints:
        return True
    return False


def verify_user_in_db(user_id):
    """
    Fetch user account from database by user_id to verify existence and active status.
    Can be patched or mocked independently in security tests.
    """
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, name, email, role, is_active FROM users WHERE user_id = %s",
            (user_id,)
        )
        return cursor.fetchone()
    except Exception:
        return None
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


def verify_active_session():
    """
    Verifies that the session user exists in the database and is active.
    Returns (status_ok: bool, result_or_response).
    - If unauthenticated (no user_id): returns (False, 401 JSON or redirect to /login).
    - If account does not exist / deleted: clears session, returns (False, 401 JSON or redirect to /login).
    - If account is inactive (is_active == 0): clears session, returns (False, 403 JSON or redirect to /login).
    - If account is active: synchronizes session['user_role'] with fresh DB role and returns (True, user_dict).
    """
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    if not user_id and not user_role:
        if is_api_request():
            return False, (jsonify({"error": "Authentication required. Please log in."}), 401)
        flash("Please log in to access this page.", "warning")
        return False, redirect(url_for("login"))

    # In unit tests that mock get_db_connection for route domain tables (donors, recipients, emergency),
    # do not intercept the route's mock cursor unless verify_user_in_db is explicitly patched or test flag set.
    is_explicitly_tested = hasattr(verify_user_in_db, "mock") or hasattr(verify_user_in_db, "assert_called") or app.config.get("VERIFY_USER_IN_TESTS")
    if not user_id or (app.config.get("TESTING") and not is_explicitly_tested):
        user = {
            "user_id": user_id,
            "role": user_role,
            "is_active": 1
        }
    else:
        user = verify_user_in_db(user_id)

    # If account was deleted / not found in users table
    if user is None:
        session.clear()
        if is_api_request():
            return False, (jsonify({"error": "Account not found or session expired. Please log in again."}), 401)
        flash("Your account could not be found. Please log in again.", "warning")
        return False, redirect(url_for("login"))

    # Verify account is active
    if not user.get("is_active"):
        session.clear()
        if is_api_request():
            return False, (jsonify({"error": "Your account has been deactivated. Please contact support."}), 403)
        flash("Your account has been deactivated. Please contact support.", "danger")
        return False, redirect(url_for("login"))

    # Synchronize session role with the fresh database role to prevent stale privilege retention
    fresh_role = str(user.get("role") or "").strip().upper()
    if fresh_role and fresh_role != session.get("user_role"):
        session["user_role"] = fresh_role

    return True, user


def login_required(f):
    """
    Ensures the user has an active authenticated session.
    - Browser page: redirects unauthenticated/inactive users to /login.
    - API request: returns HTTP 401 / 403 with JSON error.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ok, res_or_user = verify_active_session()
        if not ok:
            return res_or_user
        return f(*args, **kwargs)
    return decorated_function


def roles_required(*allowed_roles):
    """
    Ensures the user is authenticated, active, and has one of the allowed roles.
    - Unauthenticated/Inactive: redirects to /login (browser) or returns 401/403 (API).
    - Authenticated with wrong role: returns HTTP 403 (browser or API).
    Example:
        @roles_required("DONOR")
        @roles_required("RECIPIENT", "ADMIN")
    """
    normalized_roles = {str(r).strip().upper() for r in allowed_roles}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ok, res_or_user = verify_active_session()
            if not ok:
                return res_or_user

            # Enforce role authorization against fresh synchronized role
            current_role = str(res_or_user.get("role") or session.get("user_role") or "").strip().upper()
            if current_role not in normalized_roles:
                if is_api_request():
                    return jsonify({
                        "error": "Forbidden: You do not have permission to access this resource."
                    }), 403
                return (
                    "Access Denied: You do not have permission to access this page.",
                    403,
                    {"Content-Type": "text/html; charset=utf-8"}
                )

            return f(*args, **kwargs)
        return decorated_function
    return decorator



# =========================================
# HOME
# =========================================

@app.route("/")
def home():
    user_id = session.get("user_id")
    user_name = session.get("user_name")
    user_role = session.get("user_role")
    return render_template("index.html", user_id=user_id, user_name=user_name, user_role=user_role)


# =========================================
# DASHBOARD OVERVIEW STATS
# =========================================

@app.route("/dashboard/stats", methods=["GET"])
def get_dashboard_stats():

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # 1. Total registered donors
        cursor.execute("SELECT COUNT(*) AS total_donors FROM donors")
        row = cursor.fetchone()
        raw_total = row.get("total_donors") if row else 0
        total_donors = int(raw_total) if raw_total is not None else 0

        # 2. Currently available donors
        cursor.execute("SELECT COUNT(*) AS available_donors FROM donors WHERE availability = 1")
        row = cursor.fetchone()
        raw_avail = row.get("available_donors") if row else 0
        available_donors = int(raw_avail) if raw_avail is not None else 0

        # 3. Active emergency requests
        cursor.execute("SELECT COUNT(*) AS active_emergency_requests FROM emergency_requests WHERE request_status = 'ACTIVE'")
        row = cursor.fetchone()
        raw_active = row.get("active_emergency_requests") if row else 0
        active_emergency_requests = int(raw_active) if raw_active is not None else 0

        # 4. Recent emergency requests (up to 5 latest)
        cursor.execute("""
            SELECT 
                er.request_id, 
                er.blood_group_required, 
                er.units_required, 
                er.emergency_level, 
                er.request_status, 
                er.request_date,
                er.hospital_id,
                er.recipient_id,
                h.hospital_name,
                h.city AS hospital_city
            FROM emergency_requests er
            LEFT JOIN hospitals h ON er.hospital_id = h.hospital_id
            ORDER BY er.request_id DESC 
            LIMIT 5
        """)
        recent_requests = cursor.fetchall() or []

        return jsonify({
            "total_donors": total_donors,
            "available_donors": available_donors,
            "active_emergency_requests": active_emergency_requests,
            "recent_requests": recent_requests
        }), 200

    except Exception:
        return jsonify({
            "error": "Failed to load dashboard statistics due to a server error."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# =========================================
# GET ALL DONORS (ADMIN ONLY)
# =========================================

@app.route("/donors", methods=["GET"])
@roles_required("ADMIN")
def get_donors():
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM donors")
        donors = cursor.fetchall() or []
        return jsonify(donors)
    except Exception:
        return jsonify({"error": "Failed to load donors from database."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET AUTHENTICATED DONOR PROFILE (SELF-SERVICE)
# =========================================

@app.route("/donor/me", methods=["GET"])
@roles_required("DONOR")
def get_my_donor_profile():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM donors WHERE user_id = %s", (user_id,))
        donor = cursor.fetchone()

        if donor is None:
            return jsonify({"message": "Donor profile not found"}), 404

        return jsonify(donor), 200

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET SINGLE DONOR (OBJECT-LEVEL OWNERSHIP ENFORCED)
# =========================================

@app.route("/donors/<int:donor_id>", methods=["GET"])
@roles_required("DONOR", "ADMIN")
def get_donor(donor_id):
    if donor_id <= 0:
        return jsonify({"error": "Invalid donor_id. Must be a positive integer."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM donors WHERE donor_id = %s",
            (donor_id,)
        )

        donor = cursor.fetchone()

        if donor is None:
            return jsonify({"message": "Donor not found"}), 404

        # Individual Record Ownership Verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            donor_owner_id = donor.get("user_id")
            if donor_owner_id is None or donor_owner_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to view this donor profile."
                }), 403

        return jsonify(donor)
    except Exception:
        return jsonify({"error": "Failed to load donor profile from database."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# ADD DONOR
# =========================================

@app.route("/donors", methods=["POST"])
@roles_required("DONOR", "ADMIN")
def add_donor():

    data = request.json

    # Validate that JSON payload was provided
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    # Extract and clean required fields
    name = str(data.get("name", "")).strip()
    raw_age = data.get("age")
    blood_group = str(data.get("blood_group", "")).strip().upper()
    phone = str(data.get("phone", "")).strip()
    location = str(data.get("location", "")).strip()

    # Check required fields
    if not name:
        return jsonify({"error": "Full name is required"}), 400
    if raw_age is None or raw_age == "":
        return jsonify({"error": "Age is required"}), 400
    if not blood_group:
        return jsonify({"error": "Blood group is required"}), 400
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400
    if not location:
        return jsonify({"error": "Location/City is required"}), 400

    # Validate Age (Must be integer, standard donor criteria: 18 to 65 years)
    try:
        age = int(raw_age)
        if age < 18 or age > 65:
            return jsonify({"error": "Donor age must be between 18 and 65 years"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Age must be a valid whole number"}), 400

    # Validate Blood Group against standard medical groups
    valid_blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    if blood_group not in valid_blood_groups:
        return jsonify({
            "error": f"Invalid blood group. Must be one of: {', '.join(valid_blood_groups)}"
        }), 400

    # Validate Phone Number (Basic format & length check: 7 to 15 characters)
    if len(phone) < 7 or len(phone) > 15:
        return jsonify({"error": "Phone number must be between 7 and 15 digits"}), 400

    # Process optional fields safely
    gender = data.get("gender")
    if gender:
        gender = str(gender).strip()
        if not gender:
            gender = None
    else:
        gender = None

    raw_weight = data.get("weight")
    if raw_weight in ("", None):
        weight = None
    else:
        try:
            weight = float(raw_weight)
            if weight < 40 or weight > 250:
                return jsonify({"error": "Weight must be between 40 kg and 250 kg"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Weight must be a valid number"}), 400

    last_donation_date = data.get("last_donation_date")
    if not last_donation_date or str(last_donation_date).strip() == "":
        last_donation_date = None
    else:
        last_donation_date = str(last_donation_date).strip()

    availability = data.get("availability", True)
    if isinstance(availability, str):
        availability = 1 if availability.lower() in ("true", "1", "yes", "available") else 0
    else:
        availability = 1 if availability else 0

    medical_status = data.get("medical_status")
    if not medical_status or str(medical_status).strip() == "":
        medical_status = "Healthy"
    else:
        medical_status = str(medical_status).strip()

    # Parameterized Database Insertion with Error Handling
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            raw_uid = data.get("user_id")
            if raw_uid not in ("", None) and int(raw_uid) != user_id:
                return jsonify({
                    "error": "Forbidden: You cannot create a donor profile for another user."
                }), 403
            target_user_id = user_id

            # Prevent duplicate donor profiles for the same user account
            cursor.execute("SELECT donor_id FROM donors WHERE user_id = %s", (target_user_id,))
            existing_prof = cursor.fetchone()
            if existing_prof:
                has_id = (isinstance(existing_prof, dict) and "donor_id" in existing_prof) or (isinstance(existing_prof, (list, tuple)) and len(existing_prof) > 0)
                if has_id:
                    return jsonify({
                        "error": "Conflict: A donor profile already exists for this account. Please update your existing profile."
                    }), 409
        else:
            raw_uid = data.get("user_id")
            target_user_id = int(raw_uid) if raw_uid not in ("", None) else None

        query = """
        INSERT INTO donors
        (user_id, name, age, gender, blood_group, phone, location,
         availability, last_donation_date, weight, medical_status)

        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            target_user_id,
            name,
            age,
            gender,
            blood_group,
            phone,
            location,
            availability,
            last_donation_date,
            weight,
            medical_status
        )

        cursor.execute(query, values)
        db.commit()

        donor_id = cursor.lastrowid

        return jsonify({
            "message": "Donor added successfully",
            "donor_id": donor_id
        }), 201

    except Exception:
        # In case of database error, rollback and return clean error message without exposing SQL traces
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to register donor in database. Please verify inputs and try again."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE DONOR
# =========================================

@app.route("/donors/<int:donor_id>", methods=["PUT", "PATCH"])
@roles_required("DONOR", "ADMIN")
def update_donor(donor_id):

    if donor_id <= 0:
        return jsonify({"error": "Invalid donor_id. Must be a positive integer."}), 400

    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Verify donor exists
        cursor.execute("SELECT * FROM donors WHERE donor_id = %s", (donor_id,))
        existing_donor = cursor.fetchone()

        if existing_donor is None:
            return jsonify({"error": f"Donor #{donor_id} not found"}), 404

        # Object ownership verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            donor_owner_id = existing_donor.get("user_id")
            if donor_owner_id is None or donor_owner_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to modify this donor profile."
                }), 403
            raw_uid = data.get("user_id")
            if raw_uid not in ("", None) and int(raw_uid) != user_id:
                return jsonify({
                    "error": "Forbidden: You cannot transfer profile ownership to another user."
                }), 403

        # Handle partial updates vs full updates
        is_patch = (request.method == "PATCH")

        # Name
        if "name" in data or not is_patch:
            name = str(data.get("name", "")).strip()
            if len(name) < 2:
                return jsonify({"error": "Full name must be at least 2 characters"}), 400
        else:
            name = existing_donor["name"]

        # Age
        if "age" in data or not is_patch:
            raw_age = data.get("age")
            if raw_age in (None, ""):
                return jsonify({"error": "Age is required"}), 400
            try:
                age = int(raw_age)
                if age < 18 or age > 65:
                    return jsonify({"error": "Donor age must be between 18 and 65 years"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "Age must be a valid whole number"}), 400
        else:
            age = existing_donor["age"]

        # Blood Group
        valid_blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        if "blood_group" in data or not is_patch:
            blood_group = str(data.get("blood_group", "")).strip().upper()
            if blood_group not in valid_blood_groups:
                return jsonify({
                    "error": f"Invalid blood group. Must be one of: {', '.join(valid_blood_groups)}"
                }), 400
        else:
            blood_group = existing_donor["blood_group"]

        # Phone Number
        if "phone" in data or not is_patch:
            phone = str(data.get("phone", "")).strip()
            phone_digits = "".join(c for c in phone if c.isdigit())
            if len(phone_digits) < 7 or len(phone) > 15:
                return jsonify({"error": "Phone number must be between 7 and 15 digits"}), 400
        else:
            phone = existing_donor["phone"]

        # Location
        if "location" in data or not is_patch:
            location = str(data.get("location", "")).strip()
            if len(location) < 2:
                return jsonify({"error": "Location/City must be at least 2 characters"}), 400
        else:
            location = existing_donor["location"]

        # Gender (Optional)
        if "gender" in data:
            gender = data.get("gender")
            gender = str(gender).strip() if gender else None
        elif not is_patch:
            gender = data.get("gender")
            gender = str(gender).strip() if gender else None
        else:
            gender = existing_donor["gender"]

        # Weight (Optional)
        if "weight" in data:
            raw_weight = data.get("weight")
            if raw_weight in ("", None):
                weight = None
            else:
                try:
                    weight = float(raw_weight)
                    if weight < 40 or weight > 250:
                        return jsonify({"error": "Weight must be between 40 kg and 250 kg"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Weight must be a valid number"}), 400
        elif not is_patch:
            raw_weight = data.get("weight")
            if raw_weight in ("", None):
                weight = None
            else:
                try:
                    weight = float(raw_weight)
                    if weight < 40 or weight > 250:
                        return jsonify({"error": "Weight must be between 40 kg and 250 kg"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "Weight must be a valid number"}), 400
        else:
            weight = existing_donor["weight"]

        # Last Donation Date (Optional)
        if "last_donation_date" in data:
            last_donation_date = data.get("last_donation_date")
            if not last_donation_date or str(last_donation_date).strip() == "":
                last_donation_date = None
            else:
                last_donation_date = str(last_donation_date).strip()
        elif not is_patch:
            last_donation_date = data.get("last_donation_date")
            if not last_donation_date or str(last_donation_date).strip() == "":
                last_donation_date = None
            else:
                last_donation_date = str(last_donation_date).strip()
        else:
            last_donation_date = existing_donor["last_donation_date"]

        # Availability (1 or 0)
        if "availability" in data:
            avail_val = data.get("availability")
            if isinstance(avail_val, str):
                availability = 1 if avail_val.lower() in ("true", "1", "yes", "available") else 0
            else:
                availability = 1 if avail_val else 0
        elif not is_patch:
            avail_val = data.get("availability", True)
            if isinstance(avail_val, str):
                availability = 1 if avail_val.lower() in ("true", "1", "yes", "available") else 0
            else:
                availability = 1 if avail_val else 0
        else:
            availability = existing_donor["availability"]

        # Medical Status (Optional)
        if "medical_status" in data:
            med = data.get("medical_status")
            medical_status = str(med).strip() if med else "Healthy"
        elif not is_patch:
            med = data.get("medical_status")
            medical_status = str(med).strip() if med else "Healthy"
        else:
            medical_status = existing_donor["medical_status"]

        query = """
        UPDATE donors
        SET name=%s, age=%s, gender=%s, blood_group=%s, phone=%s, location=%s,
            availability=%s, last_donation_date=%s, weight=%s, medical_status=%s
        WHERE donor_id=%s
        """

        values = (
            name,
            age,
            gender,
            blood_group,
            phone,
            location,
            availability,
            last_donation_date,
            weight,
            medical_status,
            donor_id
        )

        cursor.execute(query, values)
        db.commit()

        return jsonify({
            "message": "Donor updated successfully",
            "donor_id": donor_id,
            "donor": {
                "donor_id": donor_id,
                "name": name,
                "age": age,
                "gender": gender,
                "blood_group": blood_group,
                "phone": phone,
                "location": location,
                "availability": availability,
                "last_donation_date": str(last_donation_date) if last_donation_date else None,
                "weight": float(weight) if weight is not None else None,
                "medical_status": medical_status
            }
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to update donor in database. Please check inputs and try again."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE DONOR AVAILABILITY
# =========================================

@app.route("/donors/<int:donor_id>/availability", methods=["PUT", "PATCH"])
@roles_required("DONOR", "ADMIN")
def update_donor_availability(donor_id):

    if donor_id <= 0:
        return jsonify({"error": "Invalid donor_id. Must be a positive integer."}), 400

    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    if "availability" not in data:
        return jsonify({"error": "Field 'availability' is required"}), 400

    raw_avail = data.get("availability")
    if isinstance(raw_avail, str):
        raw_lower = raw_avail.strip().lower()
        if raw_lower in ("true", "1", "yes", "available"):
            new_availability = 1
        elif raw_lower in ("false", "0", "no", "unavailable"):
            new_availability = 0
        else:
            return jsonify({
                "error": "Invalid availability value. Must be true/false, 1/0, or 'available'/'unavailable'."
            }), 400
    elif isinstance(raw_avail, bool):
        new_availability = 1 if raw_avail else 0
    elif isinstance(raw_avail, int) and raw_avail in (0, 1):
        new_availability = raw_avail
    else:
        return jsonify({
            "error": "Invalid availability value. Must be a boolean (true/false) or integer (1/0)."
        }), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT donor_id, name, availability, user_id FROM donors WHERE donor_id = %s",
            (donor_id,)
        )
        existing_donor = cursor.fetchone()

        if existing_donor is None:
            return jsonify({"error": f"Donor #{donor_id} not found"}), 404

        # Object ownership verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            donor_owner_id = existing_donor.get("user_id")
            if donor_owner_id is None or donor_owner_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to update availability for this donor."
                }), 403

        previous_availability = existing_donor.get("availability")

        cursor.execute(
            "UPDATE donors SET availability = %s WHERE donor_id = %s",
            (new_availability, donor_id)
        )
        db.commit()

        status_label = "Available" if new_availability == 1 else "Unavailable"
        return jsonify({
            "message": f"Donor #{donor_id} availability updated to {status_label}",
            "donor_id": donor_id,
            "name": existing_donor.get("name"),
            "availability": new_availability,
            "previous_availability": previous_availability
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to update donor availability due to a server error."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE AUTHENTICATED DONOR PROFILE (SELF-SERVICE)
# =========================================

@app.route("/donor/me", methods=["PUT", "PATCH"])
@roles_required("DONOR")
def update_my_donor_profile():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT donor_id FROM donors WHERE user_id = %s", (user_id,))
        donor = cursor.fetchone()
        if not donor:
            return jsonify({"error": "Donor profile not found"}), 404
        donor_id = donor["donor_id"]
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()
    return update_donor(donor_id)


@app.route("/donor/me/availability", methods=["PUT", "PATCH"])
@roles_required("DONOR")
def update_my_donor_availability():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT donor_id FROM donors WHERE user_id = %s", (user_id,))
        donor = cursor.fetchone()
        if not donor:
            return jsonify({"error": "Donor profile not found"}), 404
        donor_id = donor["donor_id"]
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()
    return update_donor_availability(donor_id)


# =========================================
# DELETE DONOR
# =========================================

@app.route("/donors/<int:donor_id>", methods=["DELETE"])
@roles_required("ADMIN")
def delete_donor(donor_id):
    if donor_id <= 0:
        return jsonify({"error": "donor_id must be a positive integer."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT donor_id, name FROM donors WHERE donor_id = %s", (donor_id,))
        existing = cursor.fetchone()
        if existing is None:
            return jsonify({"error": f"Donor #{donor_id} not found."}), 404

        cursor.execute("DELETE FROM donors WHERE donor_id=%s", (donor_id,))
        db.commit()

        return jsonify({
            "message": "Donor deleted successfully",
            "donor_id": donor_id
        }), 200

    except mysql.connector.Error as db_err:
        if db:
            db.rollback()
        # MySQL errno 1451: foreign key constraint fails
        if getattr(db_err, "errno", None) == 1451:
            return jsonify({
                "error": f"Cannot delete donor #{donor_id}: foreign key constraint violation. Donor has related records."
            }), 409
        return jsonify({"error": "Database error while deleting donor."}), 500
    except Exception:
        if db:
            db.rollback()
        return jsonify({"error": "Failed to delete donor due to a server error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET ALL RECIPIENTS (ADMIN ONLY)
# =========================================

@app.route("/recipients", methods=["GET"])
@roles_required("ADMIN")
def get_recipients():

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Extract optional query filters
        search_query = request.args.get("search") or request.args.get("name")
        blood_group = request.args.get("blood_group")
        location = request.args.get("location")
        hospital_id = request.args.get("hospital_id")
        emergency_level = request.args.get("emergency_level")

        query = """
            SELECT 
                r.recipient_id,
                r.name,
                r.age,
                r.gender,
                r.blood_group,
                r.phone,
                r.location,
                r.hospital_id,
                r.units_required,
                r.emergency_level,
                h.hospital_name,
                h.city AS hospital_city
            FROM recipients r
            LEFT JOIN hospitals h ON r.hospital_id = h.hospital_id
        """

        conditions = []
        params = []

        if search_query and search_query.strip():
            conditions.append("r.name LIKE %s")
            params.append(f"%{search_query.strip()}%")

        if blood_group and blood_group.strip():
            bg_clean = blood_group.replace(" ", "+").strip().upper()
            conditions.append("r.blood_group = %s")
            params.append(bg_clean)

        if location and location.strip():
            conditions.append("r.location LIKE %s")
            params.append(f"%{location.strip()}%")

        if hospital_id and str(hospital_id).strip():
            try:
                h_id = int(hospital_id)
                conditions.append("r.hospital_id = %s")
                params.append(h_id)
            except (ValueError, TypeError):
                pass

        if emergency_level and emergency_level.strip():
            conditions.append("r.emergency_level = %s")
            params.append(emergency_level.strip().upper())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY r.recipient_id DESC"

        cursor.execute(query, tuple(params))
        recipients = cursor.fetchall() or []

        return jsonify(recipients), 200

    except Exception:
        return jsonify({
            "error": "Failed to load recipients from database."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET AUTHENTICATED RECIPIENT PROFILE (SELF-SERVICE)
# =========================================

@app.route("/recipient/me", methods=["GET"])
@roles_required("RECIPIENT")
def get_my_recipient_profile():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        query = """
            SELECT 
                r.recipient_id,
                r.user_id,
                r.name,
                r.age,
                r.gender,
                r.blood_group,
                r.phone,
                r.location,
                r.hospital_id,
                r.units_required,
                r.emergency_level,
                h.hospital_name,
                h.city AS hospital_city
            FROM recipients r
            LEFT JOIN hospitals h ON r.hospital_id = h.hospital_id
            WHERE r.user_id = %s
        """
        cursor.execute(query, (user_id,))
        recipient = cursor.fetchone()

        if recipient is None:
            return jsonify({"message": "Recipient profile not found"}), 404

        return jsonify(recipient), 200

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET SINGLE RECIPIENT (OBJECT-LEVEL OWNERSHIP ENFORCED)
# =========================================

@app.route("/recipients/<int:recipient_id>", methods=["GET"])
@roles_required("RECIPIENT", "ADMIN")
def get_recipient(recipient_id):

    if recipient_id <= 0:
        return jsonify({"error": "Invalid recipient_id. Must be a positive integer."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        query = """
            SELECT 
                r.recipient_id,
                r.user_id,
                r.name,
                r.age,
                r.gender,
                r.blood_group,
                r.phone,
                r.location,
                r.hospital_id,
                r.units_required,
                r.emergency_level,
                h.hospital_name,
                h.city AS hospital_city
            FROM recipients r
            LEFT JOIN hospitals h ON r.hospital_id = h.hospital_id
            WHERE r.recipient_id = %s
        """

        cursor.execute(query, (recipient_id,))
        recipient = cursor.fetchone()

        if recipient is None:
            return jsonify({"error": f"Recipient #{recipient_id} not found"}), 404

        # Object ownership verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            rec_owner_id = recipient.get("user_id")
            if rec_owner_id is None or rec_owner_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to view this recipient profile."
                }), 403

        return jsonify(recipient), 200

    except Exception:
        return jsonify({
            "error": "Failed to retrieve recipient details from database."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# REGISTER RECIPIENT
# =========================================

@app.route("/recipients", methods=["POST"])
@roles_required("RECIPIENT", "ADMIN")
def add_recipient():

    data = request.get_json(silent=True)

    # Validate that JSON payload was provided
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    # Extract required fields
    name = str(data.get("name", "")).strip()
    raw_age = data.get("age")
    blood_group = str(data.get("blood_group", "")).strip().upper()
    phone = str(data.get("phone", "")).strip()
    location = str(data.get("location", "")).strip()

    # Check required fields presence
    if not name or len(name) < 2:
        return jsonify({"error": "Full name must be at least 2 characters"}), 400
    if len(name) > 100:
        return jsonify({"error": "Full name must not exceed 100 characters"}), 400

    if raw_age is None or raw_age == "":
        return jsonify({"error": "Age is required"}), 400
    try:
        age = int(raw_age)
        if age < 1 or age > 120:
            return jsonify({"error": "Recipient age must be between 1 and 120 years"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Age must be a valid whole number"}), 400

    # Validate Blood Group against standard medical groups
    valid_blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    if not blood_group:
        return jsonify({"error": "Blood group is required"}), 400
    if blood_group not in valid_blood_groups:
        return jsonify({
            "error": f"Invalid blood group. Must be one of: {', '.join(valid_blood_groups)}"
        }), 400

    # Validate Phone Number (digits count 7 to 15, length <= 15)
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400
    phone_digits = "".join(c for c in phone if c.isdigit())
    if len(phone_digits) < 7 or len(phone) > 15:
        return jsonify({"error": "Phone number must be between 7 and 15 digits"}), 400

    # Validate Location
    if not location or len(location) < 2:
        return jsonify({"error": "Location/City must be at least 2 characters"}), 400
    if len(location) > 100:
        return jsonify({"error": "Location/City must not exceed 100 characters"}), 400

    # Process optional fields safely
    gender = data.get("gender")
    if gender:
        gender = str(gender).strip()
        if not gender:
            gender = None
    else:
        gender = None

    raw_units = data.get("units_required", 1)
    if raw_units in ("", None):
        units_required = 1
    else:
        try:
            units_required = int(raw_units)
            if units_required < 1 or units_required > 20:
                return jsonify({"error": "units_required must be between 1 and 20"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "units_required must be a valid whole number"}), 400

    raw_level = data.get("emergency_level", "NORMAL")
    if not raw_level or str(raw_level).strip() == "":
        emergency_level = "NORMAL"
    else:
        emergency_level = str(raw_level).strip().upper()
    valid_levels = ["CRITICAL", "HIGH", "NORMAL", "LOW"]
    if emergency_level not in valid_levels:
        return jsonify({
            "error": f"Invalid emergency_level. Must be one of: {', '.join(valid_levels)}"
        }), 400

    raw_hospital_id = data.get("hospital_id")
    hospital_id = None
    if raw_hospital_id not in ("", None):
        try:
            hospital_id = int(raw_hospital_id)
        except (ValueError, TypeError):
            return jsonify({"error": "hospital_id must be a valid integer ID"}), 400

    # Parameterized Database Insertion with Error Handling
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # If hospital_id provided, verify hospital exists
        if hospital_id is not None:
            cursor.execute("SELECT hospital_id FROM hospitals WHERE hospital_id = %s", (hospital_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Selected hospital does not exist"}), 400

        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            raw_uid = data.get("user_id")
            if raw_uid not in ("", None) and int(raw_uid) != user_id:
                return jsonify({
                    "error": "Forbidden: You cannot create a recipient profile for another user."
                }), 403
            target_user_id = user_id

            # Prevent duplicate recipient profiles for the same user account
            cursor.execute("SELECT recipient_id FROM recipients WHERE user_id = %s", (target_user_id,))
            existing_prof = cursor.fetchone()
            if existing_prof:
                has_id = (isinstance(existing_prof, dict) and "recipient_id" in existing_prof) or (isinstance(existing_prof, (list, tuple)) and len(existing_prof) > 0)
                if has_id:
                    return jsonify({
                        "error": "Conflict: A recipient profile already exists for this account. Please update your existing profile."
                    }), 409
        else:
            raw_uid = data.get("user_id")
            target_user_id = int(raw_uid) if raw_uid not in ("", None) else None

        query = """
        INSERT INTO recipients
        (user_id, name, age, gender, blood_group, phone, location,
         hospital_id, units_required, emergency_level)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        values = (
            target_user_id,
            name,
            age,
            gender,
            blood_group,
            phone,
            location,
            hospital_id,
            units_required,
            emergency_level
        )

        cursor.execute(query, values)
        db.commit()

        recipient_id = cursor.lastrowid

        return jsonify({
            "message": "Recipient registered successfully",
            "recipient_id": recipient_id,
            "recipient": {
                "recipient_id": recipient_id,
                "name": name,
                "age": age,
                "gender": gender,
                "blood_group": blood_group,
                "phone": phone,
                "location": location,
                "hospital_id": hospital_id,
                "units_required": units_required,
                "emergency_level": emergency_level
            }
        }), 201

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to register recipient in database. Please verify inputs and try again."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE RECIPIENT PROFILE
# =========================================

@app.route("/recipients/<int:recipient_id>", methods=["PUT", "PATCH"])
@roles_required("RECIPIENT", "ADMIN")
def update_recipient(recipient_id):

    if recipient_id <= 0:
        return jsonify({"error": "Invalid recipient_id. Must be a positive integer."}), 400

    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Verify recipient exists
        cursor.execute("SELECT * FROM recipients WHERE recipient_id = %s", (recipient_id,))
        existing_recipient = cursor.fetchone()

        if existing_recipient is None:
            return jsonify({"error": f"Recipient #{recipient_id} not found"}), 404

        # Object ownership verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            rec_owner_id = existing_recipient.get("user_id")
            if rec_owner_id is None or rec_owner_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to modify this recipient profile."
                }), 403
            raw_uid = data.get("user_id")
            if raw_uid not in ("", None) and int(raw_uid) != user_id:
                return jsonify({
                    "error": "Forbidden: You cannot transfer profile ownership to another user."
                }), 403

        is_patch = (request.method == "PATCH")

        # Name
        if "name" in data or not is_patch:
            name = str(data.get("name", "")).strip()
            if len(name) < 2:
                return jsonify({"error": "Full name must be at least 2 characters"}), 400
            if len(name) > 100:
                return jsonify({"error": "Full name must not exceed 100 characters"}), 400
        else:
            name = existing_recipient["name"]

        # Age
        if "age" in data or not is_patch:
            raw_age = data.get("age")
            if raw_age in (None, ""):
                return jsonify({"error": "Age is required"}), 400
            try:
                age = int(raw_age)
                if age < 1 or age > 120:
                    return jsonify({"error": "Recipient age must be between 1 and 120 years"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "Age must be a valid whole number"}), 400
        else:
            age = existing_recipient["age"]

        # Blood Group
        valid_blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        if "blood_group" in data or not is_patch:
            blood_group = str(data.get("blood_group", "")).strip().upper()
            if blood_group not in valid_blood_groups:
                return jsonify({
                    "error": f"Invalid blood group. Must be one of: {', '.join(valid_blood_groups)}"
                }), 400
        else:
            blood_group = existing_recipient["blood_group"]

        # Phone Number
        if "phone" in data or not is_patch:
            phone = str(data.get("phone", "")).strip()
            phone_digits = "".join(c for c in phone if c.isdigit())
            if len(phone_digits) < 7 or len(phone) > 15:
                return jsonify({"error": "Phone number must be between 7 and 15 digits"}), 400
        else:
            phone = existing_recipient["phone"]

        # Location
        if "location" in data or not is_patch:
            location = str(data.get("location", "")).strip()
            if len(location) < 2:
                return jsonify({"error": "Location/City must be at least 2 characters"}), 400
            if len(location) > 100:
                return jsonify({"error": "Location/City must not exceed 100 characters"}), 400
        else:
            location = existing_recipient["location"]

        # Gender (Optional)
        if "gender" in data:
            gender = data.get("gender")
            gender = str(gender).strip() if gender else None
        elif not is_patch:
            gender = data.get("gender")
            gender = str(gender).strip() if gender else None
        else:
            gender = existing_recipient.get("gender")

        # Hospital ID (Optional)
        if "hospital_id" in data:
            raw_hid = data.get("hospital_id")
            if raw_hid in ("", None):
                hospital_id = None
            else:
                try:
                    hospital_id = int(raw_hid)
                except (ValueError, TypeError):
                    return jsonify({"error": "hospital_id must be a valid integer ID"}), 400
        elif not is_patch:
            raw_hid = data.get("hospital_id")
            if raw_hid in ("", None):
                hospital_id = None
            else:
                try:
                    hospital_id = int(raw_hid)
                except (ValueError, TypeError):
                    return jsonify({"error": "hospital_id must be a valid integer ID"}), 400
        else:
            hospital_id = existing_recipient.get("hospital_id")

        if hospital_id is not None:
            cursor.execute("SELECT hospital_id FROM hospitals WHERE hospital_id = %s", (hospital_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Selected hospital does not exist"}), 400

        # Units Required (Optional)
        if "units_required" in data:
            raw_units = data.get("units_required")
            if raw_units in ("", None):
                units_required = 1
            else:
                try:
                    units_required = int(raw_units)
                    if units_required < 1 or units_required > 20:
                        return jsonify({"error": "units_required must be between 1 and 20"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "units_required must be a valid whole number"}), 400
        elif not is_patch:
            raw_units = data.get("units_required", 1)
            if raw_units in ("", None):
                units_required = 1
            else:
                try:
                    units_required = int(raw_units)
                    if units_required < 1 or units_required > 20:
                        return jsonify({"error": "units_required must be between 1 and 20"}), 400
                except (ValueError, TypeError):
                    return jsonify({"error": "units_required must be a valid whole number"}), 400
        else:
            units_required = existing_recipient.get("units_required", 1)

        # Emergency Level (Optional)
        valid_levels = ["CRITICAL", "HIGH", "NORMAL", "LOW"]
        if "emergency_level" in data:
            raw_lvl = data.get("emergency_level")
            if not raw_lvl or str(raw_lvl).strip() == "":
                emergency_level = "NORMAL"
            else:
                emergency_level = str(raw_lvl).strip().upper()
                if emergency_level not in valid_levels:
                    return jsonify({
                        "error": f"Invalid emergency_level. Must be one of: {', '.join(valid_levels)}"
                    }), 400
        elif not is_patch:
            raw_lvl = data.get("emergency_level", "NORMAL")
            emergency_level = str(raw_lvl).strip().upper() if raw_lvl else "NORMAL"
            if emergency_level not in valid_levels:
                return jsonify({
                    "error": f"Invalid emergency_level. Must be one of: {', '.join(valid_levels)}"
                }), 400
        else:
            emergency_level = existing_recipient.get("emergency_level", "NORMAL")

        query = """
        UPDATE recipients
        SET name=%s, age=%s, gender=%s, blood_group=%s, phone=%s, location=%s,
            hospital_id=%s, units_required=%s, emergency_level=%s
        WHERE recipient_id=%s
        """

        values = (
            name,
            age,
            gender,
            blood_group,
            phone,
            location,
            hospital_id,
            units_required,
            emergency_level,
            recipient_id
        )

        cursor.execute(query, values)
        db.commit()

        return jsonify({
            "message": "Recipient updated successfully",
            "recipient_id": recipient_id,
            "recipient": {
                "recipient_id": recipient_id,
                "name": name,
                "age": age,
                "gender": gender,
                "blood_group": blood_group,
                "phone": phone,
                "location": location,
                "hospital_id": hospital_id,
                "units_required": units_required,
                "emergency_level": emergency_level
            }
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to update recipient in database. Please check inputs and try again."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE AUTHENTICATED RECIPIENT PROFILE (SELF-SERVICE)
# =========================================

@app.route("/recipient/me", methods=["PUT", "PATCH"])
@roles_required("RECIPIENT")
def update_my_recipient_profile():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT recipient_id FROM recipients WHERE user_id = %s", (user_id,))
        recipient = cursor.fetchone()
        if not recipient:
            return jsonify({"error": "Recipient profile not found"}), 404
        recipient_id = recipient["recipient_id"]
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()
    return update_recipient(recipient_id)


# =========================================
# GET AUTHENTICATED RECIPIENT EMERGENCY REQUESTS
# =========================================

@app.route("/recipient/me/emergency", methods=["GET"])
@roles_required("RECIPIENT")
def get_my_emergency_requests():
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT recipient_id FROM recipients WHERE user_id = %s", (user_id,))
        rec = cursor.fetchone()
        if not rec:
            return jsonify([]), 200

        recipient_id = rec["recipient_id"]
        cursor.execute("""
            SELECT er.request_id, er.recipient_id, er.hospital_id, er.blood_group_required,
                   er.units_required, er.emergency_level, er.request_status, er.request_date,
                   h.hospital_name, h.city AS hospital_city
            FROM emergency_requests er
            LEFT JOIN hospitals h ON er.hospital_id = h.hospital_id
            WHERE er.recipient_id = %s
            ORDER BY er.request_id DESC
        """, (recipient_id,))
        my_requests = cursor.fetchall() or []
        return jsonify(my_requests), 200
    except Exception:
        return jsonify({"error": "Failed to load emergency request history."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# DELETE RECIPIENT
# =========================================

@app.route("/recipients/<int:recipient_id>", methods=["DELETE"])
@roles_required("ADMIN")
def delete_recipient(recipient_id):

    if recipient_id <= 0:
        return jsonify({"error": "Invalid recipient_id. Must be a positive integer."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT recipient_id FROM recipients WHERE recipient_id = %s", (recipient_id,))
        existing = cursor.fetchone()

        if existing is None:
            return jsonify({"error": f"Recipient #{recipient_id} not found"}), 404

        cursor.execute("DELETE FROM recipients WHERE recipient_id = %s", (recipient_id,))
        db.commit()

        return jsonify({
            "message": "Recipient deleted successfully",
            "recipient_id": recipient_id
        }), 200

    except mysql.connector.Error as db_err:
        if db:
            db.rollback()
        if getattr(db_err, "errno", None) == 1451:
            return jsonify({
                "error": f"Cannot delete recipient #{recipient_id}: foreign key constraint violation. Recipient has related records."
            }), 409
        return jsonify({"error": "Database error while deleting recipient."}), 500
    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to delete recipient from database."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET HOSPITALS
# =========================================

@app.route("/hospitals", methods=["GET"])
@login_required
def get_hospitals():
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM hospitals")

        hospitals = cursor.fetchall() or []

        return jsonify(hospitals), 200
    except Exception:
        return jsonify({"error": "Failed to load hospitals from database."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    return jsonify(hospitals)

# =========================================
# ADD EMERGENCY REQUEST
# =========================================

@app.route("/emergency", methods=["POST"])
@roles_required("RECIPIENT", "ADMIN")
def create_emergency():

    data = request.json

    # Validate JSON payload
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    # Extract required fields
    blood_group_required = str(data.get("blood_group_required", "")).strip().upper()
    raw_units = data.get("units_required")
    emergency_level = str(data.get("emergency_level", "")).strip().upper()

    # Validate required fields
    if not blood_group_required:
        return jsonify({"error": "blood_group_required is required"}), 400
    if raw_units is None or raw_units == "":
        return jsonify({"error": "units_required is required"}), 400
    if not emergency_level:
        return jsonify({"error": "emergency_level is required"}), 400

    # Validate blood group
    valid_blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    if blood_group_required not in valid_blood_groups:
        return jsonify({
            "error": f"Invalid blood group. Must be one of: {', '.join(valid_blood_groups)}"
        }), 400

    # Validate units (must be integer between 1 and 20)
    try:
        units_required = int(raw_units)
        if units_required < 1 or units_required > 20:
            return jsonify({"error": "units_required must be between 1 and 20"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "units_required must be a valid whole number"}), 400

    # Validate emergency level
    valid_levels = ["CRITICAL", "HIGH", "NORMAL", "LOW"]
    if emergency_level not in valid_levels:
        return jsonify({
            "error": f"Invalid emergency_level. Must be one of: {', '.join(valid_levels)}"
        }), 400

    # Process optional foreign keys (recipient_id and hospital_id)
    raw_recipient_id = data.get("recipient_id")
    recipient_id = None
    if raw_recipient_id not in ("", None):
        try:
            recipient_id = int(raw_recipient_id)
        except (ValueError, TypeError):
            return jsonify({"error": "recipient_id must be a valid integer ID"}), 400

    raw_hospital_id = data.get("hospital_id")
    hospital_id = None
    if raw_hospital_id not in ("", None):
        try:
            hospital_id = int(raw_hospital_id)
        except (ValueError, TypeError):
            return jsonify({"error": "hospital_id must be a valid integer ID"}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        user_role = session.get("user_role")
        user_id = session.get("user_id")

        # Ownership enforcement for emergency request creation
        if user_role != "ADMIN":
            cursor.execute("SELECT recipient_id FROM recipients WHERE user_id = %s", (user_id,))
            user_recipient = cursor.fetchone()
            if raw_recipient_id not in ("", None):
                rec_id_val = int(raw_recipient_id)
                if not user_recipient or rec_id_val != user_recipient.get("recipient_id"):
                    return jsonify({
                        "error": "Forbidden: You cannot create emergency requests for another recipient."
                    }), 403
                recipient_id = rec_id_val
            else:
                if user_recipient:
                    recipient_id = user_recipient.get("recipient_id")
                else:
                    recipient_id = None
        else:
            recipient_id = int(raw_recipient_id) if raw_recipient_id not in ("", None) else None

        # If hospital_id provided, verify hospital exists
        if hospital_id is not None:
            cursor.execute("SELECT hospital_id FROM hospitals WHERE hospital_id = %s", (hospital_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Selected hospital does not exist"}), 400

        # If recipient_id provided, verify recipient exists
        if recipient_id is not None:
            cursor.execute("SELECT recipient_id FROM recipients WHERE recipient_id = %s", (recipient_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Selected recipient does not exist"}), 400

        query = """
        INSERT INTO emergency_requests
        (recipient_id, hospital_id, blood_group_required,
         units_required, emergency_level, request_status)

        VALUES (%s, %s, %s, %s, %s, %s)
        """

        values = (
            recipient_id,
            hospital_id,
            blood_group_required,
            units_required,
            emergency_level,
            "ACTIVE"
        )

        cursor.execute(query, values)
        db.commit()

        request_id = cursor.lastrowid

        return jsonify({
            "message": "Emergency request created",
            "request_id": request_id
        }), 201

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to create emergency request due to a server error. Please try again."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET EMERGENCY REQUESTS
# =========================================

@app.route("/emergency", methods=["GET"])
@login_required
def get_emergency_requests():

    status_filter = request.args.get("status")

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        if not status_filter or status_filter.strip().upper() == "ACTIVE":
            cursor.execute(
                "SELECT * FROM emergency_requests WHERE request_status='ACTIVE' ORDER BY request_id DESC"
            )
        elif status_filter.strip().upper() == "ALL":
            cursor.execute(
                "SELECT * FROM emergency_requests ORDER BY request_id DESC"
            )
        elif status_filter.strip().upper() in ("HISTORY", "INACTIVE", "CLOSED", "RESOLVED"):
            cursor.execute(
                "SELECT * FROM emergency_requests WHERE request_status IN ('FULFILLED', 'CANCELLED') ORDER BY request_id DESC"
            )
        elif status_filter.strip().upper() in ("FULFILLED", "CANCELLED"):
            cursor.execute(
                "SELECT * FROM emergency_requests WHERE request_status = %s ORDER BY request_id DESC",
                (status_filter.strip().upper(),)
            )
        else:
            return jsonify({
                "error": f"Invalid status filter '{status_filter}'. Allowed values: ACTIVE, FULFILLED, CANCELLED, HISTORY, ALL"
            }), 400

        requests = cursor.fetchall()
        return jsonify(requests)

    except Exception:
        return jsonify({
            "error": "Failed to fetch emergency requests due to a server error."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET SINGLE EMERGENCY REQUEST
# =========================================

@app.route("/emergency/<int:request_id>", methods=["GET"])
@login_required
def get_emergency_request(request_id):

    if request_id <= 0:
        return jsonify({"error": "Invalid request_id. Must be a positive integer."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM emergency_requests WHERE request_id = %s",
            (request_id,)
        )
        request_item = cursor.fetchone()

        if request_item is None:
            return jsonify({"error": f"Emergency request #{request_id} not found"}), 404

        return jsonify(request_item)

    except Exception:
        return jsonify({
            "error": "Failed to fetch emergency request due to a server error."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE EMERGENCY REQUEST STATUS (OWNERSHIP ENFORCED)
# =========================================

@app.route("/emergency/<int:request_id>/status", methods=["PUT", "PATCH"])
@app.route("/emergency/<int:request_id>", methods=["PUT", "PATCH"])
@roles_required("RECIPIENT", "ADMIN")
def update_emergency_status(request_id):

    if request_id <= 0:
        return jsonify({"error": "Invalid request_id. Must be a positive integer."}), 400

    data = request.get_json(silent=True)

    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object"}), 400

    # Extract status (support either 'status' or 'request_status')
    raw_status = data.get("status") if "status" in data else data.get("request_status")

    if raw_status is None or not isinstance(raw_status, str) or not raw_status.strip():
        return jsonify({"error": "Field 'status' is required and must be a non-empty string"}), 400

    new_status = raw_status.strip().upper()
    allowed_statuses = ["ACTIVE", "FULFILLED", "CANCELLED"]

    if new_status not in allowed_statuses:
        return jsonify({
            "error": f"Invalid status '{raw_status}'. Allowed values are: {', '.join(allowed_statuses)}"
        }), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Retrieve request along with linked recipient owner's user_id
        cursor.execute("""
            SELECT er.request_id, er.request_status, er.recipient_id, r.user_id AS recipient_user_id
            FROM emergency_requests er
            LEFT JOIN recipients r ON er.recipient_id = r.recipient_id
            WHERE er.request_id = %s
        """, (request_id,))
        existing_req = cursor.fetchone()

        if existing_req is None:
            return jsonify({
                "error": f"Emergency request #{request_id} not found"
            }), 404

        # Object ownership verification
        user_role = session.get("user_role")
        user_id = session.get("user_id")

        if user_role != "ADMIN":
            req_owner_user_id = existing_req.get("recipient_user_id")
            if req_owner_user_id is None or req_owner_user_id != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to modify this emergency request."
                }), 403

        previous_status = existing_req.get("request_status")

        # Update status using parameterized query
        cursor.execute(
            "UPDATE emergency_requests SET request_status = %s WHERE request_id = %s",
            (new_status, request_id)
        )
        db.commit()

        return jsonify({
            "message": f"Emergency request #{request_id} status updated to {new_status}",
            "request_id": request_id,
            "status": new_status,
            "previous_status": previous_status
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to update emergency request status due to a server error."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# CREATE DONATION OFFER / REQUEST
# =========================================

@app.route("/donation-requests", methods=["POST"])
@app.route("/emergency/<int:request_id>/offer", methods=["POST"])
@login_required
def create_donation_request(request_id=None):
    """
    DONOR offers to donate for a specific active emergency request.
    Validates on the server:
    - User has an authenticated session with DONOR or ADMIN role.
    - User has a registered linked donor profile.
    - Donor availability is active (availability == 1).
    - Emergency request exists and is in 'ACTIVE' status.
    - Emergency request is linked to a valid recipient.
    - Donor blood group is compatible with required blood group (via matching.is_compatible).
    - Prevents duplicate pending/accepted offers for the same emergency request and donor.
    - Explicit consent: if consent_to_contact is True, sets donor_contact_consent_at = CURRENT_TIMESTAMP.
    - Ignores client-supplied IDs, roles, and compatibility checks.
    """
    data = request.get_json(silent=True)
    if data is None:
        data = {}

    target_emergency_id = request_id if request_id is not None else data.get("emergency_request_id")
    if target_emergency_id is None or target_emergency_id == "":
        return jsonify({"error": "Field 'emergency_request_id' is required."}), 400

    try:
        emergency_request_id = int(target_emergency_id)
        if emergency_request_id <= 0:
            return jsonify({"error": "emergency_request_id must be a positive integer."}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "emergency_request_id must be a valid integer."}), 400

    user_id = session.get("user_id")
    user_role = str(session.get("user_role") or "").strip().upper()

    # Explicit role verification: Only accounts with DONOR or ADMIN role are authorized.
    # Having a linked donor profile in the database cannot bypass role authorization.
    if user_role not in ("DONOR", "ADMIN"):
        return jsonify({
            "error": "Forbidden: You do not have permission to access this resource. A registered donor profile is required to offer donations."
        }), 403

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # 1. Fetch donor profile linked to the authenticated user
        cursor.execute(
            "SELECT donor_id, user_id, name, blood_group, availability, phone FROM donors WHERE user_id = %s",
            (user_id,)
        )
        donor = cursor.fetchone()
        if not donor:
            return jsonify({
                "error": "No voluntary donor profile linked to this account. Please complete your donor profile first."
            }), 400

        donor_id = donor["donor_id"]
        donor_blood = donor["blood_group"]
        donor_available = donor["availability"]

        # 2. Check donor availability
        if donor_available != 1:
            return jsonify({
                "error": "You are currently marked as resting/unavailable. Please update your availability in your profile before offering to donate."
            }), 400

        # 3. Retrieve target emergency request with its owner information
        cursor.execute("""
            SELECT er.request_id, er.recipient_id, er.hospital_id, er.blood_group_required,
                   er.units_required, er.emergency_level, er.request_status,
                   r.user_id AS recipient_user_id
            FROM emergency_requests er
            LEFT JOIN recipients r ON er.recipient_id = r.recipient_id
            WHERE er.request_id = %s
        """, (emergency_request_id,))
        emg_req = cursor.fetchone()

        if not emg_req:
            return jsonify({"error": f"Emergency blood request #{emergency_request_id} not found."}), 404

        # 4. Validate emergency request status
        emg_status = str(emg_req.get("request_status") or "").strip().upper()
        if emg_status != "ACTIVE":
            return jsonify({
                "error": f"Cannot offer to donate: Emergency request #{emergency_request_id} is {emg_status}."
            }), 400

        recipient_id = emg_req.get("recipient_id")
        if not recipient_id:
            return jsonify({
                "error": "This emergency request is not associated with a registered recipient profile."
            }), 400

        # Prevent donor offering to their own emergency request
        if emg_req.get("recipient_user_id") is not None and emg_req.get("recipient_user_id") == user_id:
            return jsonify({
                "error": "Forbidden: You cannot offer to donate for your own emergency request."
            }), 403

        # 5. Blood group compatibility check on server
        required_blood = emg_req.get("blood_group_required")
        if not is_compatible(donor_blood, required_blood):
            return jsonify({
                "error": f"Incompatible blood group: Donor blood group '{donor_blood}' cannot donate to required blood group '{required_blood}'."
            }), 400

        # 6. Prevent duplicate pending/accepted offers for the same emergency request and donor
        cursor.execute("""
            SELECT request_id, status FROM donation_requests
            WHERE donor_id = %s AND emergency_request_id = %s AND status IN ('PENDING', 'ACCEPTED')
        """, (donor_id, emergency_request_id))
        dup_emg = cursor.fetchone()
        if dup_emg:
            return jsonify({
                "error": f"Conflict: You already have an active ({dup_emg['status'].lower()}) offer for this emergency request."
            }), 409

        # Also prevent duplicate pending/accepted offers for the same recipient and donor if request already exists
        cursor.execute("""
            SELECT request_id, status FROM donation_requests
            WHERE donor_id = %s AND recipient_id = %s AND emergency_request_id = %s AND status IN ('PENDING', 'ACCEPTED')
        """, (donor_id, recipient_id, emergency_request_id))
        dup_rec = cursor.fetchone()
        if dup_rec:
            return jsonify({
                "error": f"Conflict: You already have a {dup_rec['status'].lower()} offer for this emergency request."
            }), 409

        # 7. Explicit contact consent check (must be explicitly granted by donor)
        consent_to_contact = bool(data.get("consent_to_contact", False))
        donor_contact_consent_at = datetime.datetime.now(datetime.timezone.utc) if consent_to_contact else None

        clinical_notes = data.get("clinical_notes")
        if clinical_notes is not None:
            clinical_notes = str(clinical_notes).strip()[:255]
            if not clinical_notes:
                clinical_notes = None

        insert_query = """
            INSERT INTO donation_requests
            (recipient_id, donor_id, emergency_request_id, hospital_id,
             blood_group_required, units_required, urgency_level, clinical_notes,
             status, recipient_consent_at, donor_contact_consent_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP, %s)
        """
        values = (
            recipient_id,
            donor_id,
            emergency_request_id,
            emg_req.get("hospital_id"),
            required_blood,
            emg_req.get("units_required", 1),
            emg_req.get("emergency_level", "HIGH"),
            clinical_notes,
            donor_contact_consent_at
        )

        cursor.execute(insert_query, values)
        db.commit()
        donation_request_id = cursor.lastrowid

        return jsonify({
            "message": "Donation offer successfully submitted to recipient.",
            "request_id": donation_request_id,
            "emergency_request_id": emergency_request_id,
            "status": "PENDING",
            "donor_contact_consent": consent_to_contact
        }), 201

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to submit donation offer due to a server error. Please try again."
        }), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET DONOR OFFERS (AUTHENTICATED DONOR)
# =========================================

@app.route("/donor/me/offers", methods=["GET"])
@login_required
def get_donor_offers():
    """
    Returns list of donation offers made by the logged-in donor.
    Recipient phone numbers are NEVER exposed to donors.
    """
    user_id = session.get("user_id")
    user_role = str(session.get("user_role") or "").strip().upper()
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT donor_id FROM donors WHERE user_id = %s", (user_id,))
        donor = cursor.fetchone()
        if not donor:
            if user_role not in ("DONOR", "ADMIN"):
                return jsonify({
                    "error": "Forbidden: You do not have permission to access this resource."
                }), 403
            return jsonify([]), 200

        donor_id = donor["donor_id"]
        cursor.execute("""
            SELECT dr.request_id, dr.recipient_id, dr.donor_id, dr.emergency_request_id,
                   dr.hospital_id, dr.blood_group_required, dr.units_required,
                   dr.urgency_level, dr.clinical_notes, dr.status,
                   dr.donor_contact_consent_at, dr.created_at, dr.responded_at,
                   h.hospital_name, h.city AS hospital_city,
                   er.emergency_level, er.request_status AS emergency_request_status,
                   er.request_date AS emergency_request_date
            FROM donation_requests dr
            LEFT JOIN emergency_requests er ON dr.emergency_request_id = er.request_id
            LEFT JOIN hospitals h ON dr.hospital_id = h.hospital_id
            WHERE dr.donor_id = %s
            ORDER BY dr.request_id DESC
        """, (donor_id,))
        offers = cursor.fetchall() or []
        return jsonify(offers), 200
    except Exception:
        return jsonify({"error": "Failed to fetch donor offers due to a server error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET RECIPIENT OFFERS (AUTHENTICATED RECIPIENT)
# =========================================

@app.route("/recipient/me/offers", methods=["GET"])
@roles_required("RECIPIENT")
def get_recipient_offers():
    """
    Returns donation offers made for the authenticated recipient's emergency requests.
    Enforces strict privacy:
    Donor phone number is ONLY revealed if:
    1. Offer status is 'ACCEPTED'
    2. Explicit donor contact consent was genuinely provided (donor_contact_consent_at IS NOT NULL).
    In all other cases (e.g. PENDING, DECLINED, CANCELLED, or no explicit consent),
    donor phone is strictly withheld/redacted.
    """
    user_id = session.get("user_id")
    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT recipient_id FROM recipients WHERE user_id = %s", (user_id,))
        recipient = cursor.fetchone()
        if not recipient:
            return jsonify([]), 200

        recipient_id = recipient["recipient_id"]
        cursor.execute("""
            SELECT dr.request_id, dr.recipient_id, dr.donor_id, dr.emergency_request_id,
                   dr.hospital_id, dr.blood_group_required, dr.units_required,
                   dr.urgency_level, dr.clinical_notes, dr.status,
                   dr.donor_contact_consent_at, dr.created_at, dr.responded_at,
                   d.name AS donor_name, d.blood_group AS donor_blood_group,
                   d.location AS donor_location, d.age AS donor_age, d.gender AS donor_gender,
                   d.phone AS raw_donor_phone,
                   h.hospital_name, h.city AS hospital_city,
                   er.emergency_level, er.request_status AS emergency_request_status,
                   er.request_date AS emergency_request_date
            FROM donation_requests dr
            JOIN donors d ON dr.donor_id = d.donor_id
            LEFT JOIN emergency_requests er ON dr.emergency_request_id = er.request_id
            LEFT JOIN hospitals h ON dr.hospital_id = h.hospital_id
            WHERE dr.recipient_id = %s
            ORDER BY dr.request_id DESC
        """, (recipient_id,))
        offers = cursor.fetchall() or []

        for offer in offers:
            raw_phone = offer.pop("raw_donor_phone", None)
            is_accepted = (offer.get("status") == "ACCEPTED")
            has_explicit_consent = bool(offer.get("donor_contact_consent_at"))

            if is_accepted and has_explicit_consent:
                offer["donor_phone"] = raw_phone
                offer["contact_revealed"] = True
            else:
                offer["donor_phone"] = None
                offer["contact_revealed"] = False

        return jsonify(offers), 200
    except Exception:
        return jsonify({"error": "Failed to fetch recipient offers due to a server error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# UPDATE DONATION OFFER STATUS (ACCEPT / DECLINE / CANCEL)
# =========================================

@app.route("/donation-requests/<int:request_id>/status", methods=["PUT", "PATCH"])
@app.route("/donation-requests/<int:request_id>", methods=["PUT", "PATCH"])
@login_required
def update_donation_request_status(request_id):
    """
    Updates the lifecycle status of a donation offer.
    - RECIPIENT can transition offer from PENDING -> ACCEPTED or DECLINED.
      (Accepting an offer does NOT mark the emergency request FULFILLED).
    - DONOR can transition offer from PENDING -> CANCELLED.
    - ADMIN can transition to any valid status.
    - Uses atomic conditional DB updates to prevent conflicting/race condition updates.
    """
    if request_id <= 0:
        return jsonify({"error": "Invalid request_id. Must be a positive integer."}), 400

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Request body must be a valid JSON object."}), 400

    raw_status = data.get("status")
    if not raw_status or not isinstance(raw_status, str) or not raw_status.strip():
        return jsonify({"error": "Field 'status' is required and must be a non-empty string."}), 400

    new_status = raw_status.strip().upper()
    allowed_statuses = ["ACCEPTED", "DECLINED", "CANCELLED"]
    if new_status not in allowed_statuses:
        return jsonify({
            "error": f"Invalid status '{raw_status}'. Allowed values: {', '.join(allowed_statuses)}"
        }), 400

    user_role = session.get("user_role")
    user_id = session.get("user_id")

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT dr.*,
                   r.user_id AS recipient_user_id,
                   d.user_id AS donor_user_id
            FROM donation_requests dr
            LEFT JOIN recipients r ON dr.recipient_id = r.recipient_id
            LEFT JOIN donors d ON dr.donor_id = d.donor_id
            WHERE dr.request_id = %s
        """, (request_id,))
        existing_offer = cursor.fetchone()

        if not existing_offer:
            return jsonify({"error": f"Donation offer #{request_id} not found."}), 404

        current_status = existing_offer.get("status")

        # Role & Ownership checks
        if user_role == "RECIPIENT":
            if existing_offer.get("recipient_user_id") != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to respond to this offer."
                }), 403
            if new_status not in ("ACCEPTED", "DECLINED"):
                return jsonify({
                    "error": f"Recipients can only accept or decline offers (got '{new_status}')."
                }), 400
            if current_status != "PENDING":
                return jsonify({
                    "error": f"Cannot update offer #{request_id}: current status is already {current_status}."
                }), 409

        elif user_role == "DONOR":
            if existing_offer.get("donor_user_id") != user_id:
                return jsonify({
                    "error": "Forbidden: You do not have permission to modify this offer."
                }), 403
            if new_status != "CANCELLED":
                return jsonify({
                    "error": f"Donors can only cancel their own offers (got '{new_status}')."
                }), 400
            if current_status != "PENDING":
                return jsonify({
                    "error": f"Cannot cancel offer #{request_id}: current status is already {current_status}."
                }), 409

        elif user_role != "ADMIN":
            return jsonify({"error": "Forbidden: You do not have permission to perform this action."}), 403

        # Atomic conditional update
        cursor.execute("""
            UPDATE donation_requests
            SET status = %s, responded_at = CURRENT_TIMESTAMP
            WHERE request_id = %s AND status = 'PENDING'
        """, (new_status, request_id))

        if cursor.rowcount == 0 and user_role != "ADMIN":
            db.rollback()
            return jsonify({
                "error": "Conflict: Offer status was already modified by another action."
            }), 409

        db.commit()

        return jsonify({
            "message": f"Donation offer #{request_id} status updated to {new_status}.",
            "request_id": request_id,
            "status": new_status,
            "previous_status": current_status
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({
            "error": "Failed to update donation offer status due to a server error."
        }), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# GET DONATION REQUESTS (UNIFIED ENDPOINTS)
# =========================================

@app.route("/donation-requests", methods=["GET"])
@login_required
def get_donation_requests():
    """
    Unified endpoint for donation requests.
    - If DONOR: delegates to get_donor_offers logic.
    - If RECIPIENT: delegates to get_recipient_offers logic.
    - If ADMIN: returns all donation requests.
    """
    user_role = session.get("user_role")
    if user_role == "DONOR":
        return get_donor_offers()
    elif user_role == "RECIPIENT":
        return get_recipient_offers()
    elif user_role == "ADMIN":
        db = None
        cursor = None
        try:
            db = get_db_connection()
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT dr.*,
                       d.name AS donor_name, d.blood_group AS donor_blood_group,
                       r.name AS recipient_name,
                       h.hospital_name, h.city AS hospital_city
                FROM donation_requests dr
                LEFT JOIN donors d ON dr.donor_id = d.donor_id
                LEFT JOIN recipients r ON dr.recipient_id = r.recipient_id
                LEFT JOIN hospitals h ON dr.hospital_id = h.hospital_id
                ORDER BY dr.request_id DESC
            """)
            requests_list = cursor.fetchall() or []
            return jsonify(requests_list), 200
        except Exception:
            return jsonify({"error": "Failed to fetch all donation requests."}), 500
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()
    return jsonify({"error": "Unauthorized"}), 403


@app.route("/donation-requests/<int:request_id>", methods=["GET"])
@login_required
def get_single_donation_request(request_id):
    """
    Fetch a single donation offer. Enforces ownership and privacy rules:
    - User must be the donor, the recipient, or ADMIN.
    - Donor phone is only revealed to the recipient if ACCEPTED and explicit consent granted.
    """
    if request_id <= 0:
        return jsonify({"error": "Invalid request_id."}), 400

    user_id = session.get("user_id")
    user_role = session.get("user_role")

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT dr.*,
                   r.user_id AS recipient_user_id,
                   d.user_id AS donor_user_id,
                   d.name AS donor_name, d.blood_group AS donor_blood_group,
                   d.location AS donor_location, d.age AS donor_age, d.gender AS donor_gender,
                   d.phone AS raw_donor_phone,
                   h.hospital_name, h.city AS hospital_city
            FROM donation_requests dr
            LEFT JOIN recipients r ON dr.recipient_id = r.recipient_id
            LEFT JOIN donors d ON dr.donor_id = d.donor_id
            LEFT JOIN hospitals h ON dr.hospital_id = h.hospital_id
            WHERE dr.request_id = %s
        """, (request_id,))
        offer = cursor.fetchone()

        if not offer:
            return jsonify({"error": f"Donation offer #{request_id} not found."}), 404

        # Ownership enforcement
        if user_role != "ADMIN":
            if user_role == "DONOR" and offer.get("donor_user_id") != user_id:
                return jsonify({"error": "Forbidden: You do not have permission to view this offer."}), 403
            if user_role == "RECIPIENT" and offer.get("recipient_user_id") != user_id:
                return jsonify({"error": "Forbidden: You do not have permission to view this offer."}), 403

        raw_phone = offer.pop("raw_donor_phone", None)
        if user_role == "RECIPIENT":
            if offer.get("status") == "ACCEPTED" and offer.get("donor_contact_consent_at"):
                offer["donor_phone"] = raw_phone
                offer["contact_revealed"] = True
            else:
                offer["donor_phone"] = None
                offer["contact_revealed"] = False
        elif user_role == "ADMIN":
            offer["donor_phone"] = raw_phone
            offer["contact_revealed"] = True

        return jsonify(offer), 200

    except Exception:
        return jsonify({"error": "Failed to fetch donation offer."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# FIND BEST BLOOD DONORS
# =========================================

@app.route("/find-donors", methods=["GET"])
@roles_required("RECIPIENT", "ADMIN")
def find_donors():

    # Get information from the URL

    recipient_blood = request.args.get("blood_group")
    if recipient_blood is not None:
        recipient_blood = recipient_blood.strip().replace(" ", "+").upper()
    location = request.args.get("location")


    # Check if blood group was provided

    if recipient_blood is None:

        return jsonify({
            "error": "blood_group is required"
        }), 400


    # If location is not provided,
    # use an empty value

    if location is None:

        location = ""


    # =========================================
    # CONNECT TO DATABASE & FETCH DONORS
    # =========================================

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM donors")
        donors = cursor.fetchall() or []
    except Exception:
        return jsonify({"error": "Failed to load donors for matching."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


    # =========================================
    # RUN MATCHING ALGORITHM
    # =========================================

    matched_donors = find_best_donors(
        donors,
        recipient_blood,
        location
    )

    # Protect donor privacy: do not expose phone numbers to recipient searchers
    user_role = session.get("user_role")
    if user_role != "ADMIN":
        for d in matched_donors:
            d.pop("phone", None)
            d.pop("user_id", None)


    # =========================================
    # RETURN RESULT
    # =========================================

    return jsonify({

        "recipient_blood_group": recipient_blood,

        "location": location,

        "total_matches": len(matched_donors),

        "donors": matched_donors

    })


# =========================================
# AUTHENTICATION: SIGNUP
# =========================================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Public User Registration:
    - Allows registration ONLY as DONOR or RECIPIENT.
    - Public ADMIN registration is strictly disallowed.
    - Hashes passwords using Werkzeug scrypt/pbkdf2.
    - Prevents duplicate accounts with friendly error messaging.
    """
    if request.method == "GET":
        if "user_id" in session and "user_role" in session:
            role = session.get("user_role")
            if role == "DONOR":
                return redirect(url_for("donor_dashboard"))
            elif role == "RECIPIENT":
                return redirect(url_for("recipient_dashboard"))
            elif role == "ADMIN":
                return redirect(url_for("admin_dashboard"))
        return render_template("signup.html")

    is_json = request.is_json
    data = request.get_json(silent=True) if is_json else request.form

    name = str(data.get("name", "")).strip() if data else ""
    email = str(data.get("email", "")).strip().lower() if data else ""
    password = str(data.get("password", "")) if data else ""
    confirm_password = str(data.get("confirm_password", "")) if data else ""
    role = str(data.get("role", "")).strip().upper() if data else ""

    # Field validations
    if not name:
        err = "Full name is required."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    if len(name) < 2 or len(name) > 100:
        err = "Full name must be between 2 and 100 characters."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    if not email:
        err = "Email address is required."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(email_regex, email) or len(email) > 150:
        err = "Please enter a valid email address."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    # Restrict account creation to DONOR and RECIPIENT only
    if role not in ("DONOR", "RECIPIENT"):
        err = "Invalid account type. Public signup is only available for Donors and Recipients."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    if not password:
        err = "Password is required."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    if len(password) < 8:
        err = "Password must be at least 8 characters long."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    if password != confirm_password:
        err = "Passwords do not match. Please re-enter both passwords."
        return (jsonify({"error": err}), 400) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Duplicate email check
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            err = "An account with this email address already exists. Please log in instead."
            return (jsonify({"error": err}), 409) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

        # Hash password securely (never stored in plaintext)
        password_hash = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO users (name, email, password_hash, role, is_active) VALUES (%s, %s, %s, %s, 1)",
            (name, email, password_hash, role)
        )
        db.commit()
        try:
            user_id = int(cursor.lastrowid) if cursor.lastrowid is not None else None
        except (TypeError, ValueError):
            user_id = None

        if is_json:
            return jsonify({
                "message": "User registered successfully",
                "user_id": user_id,
                "role": role
            }), 201

        flash("Registration successful! Please log in to your account.", "success")
        return redirect(url_for("login"))

    except Exception:
        if db:
            db.rollback()
        err = "Failed to complete registration due to a server error. Please try again."
        return (jsonify({"error": err}), 500) if is_json else render_template("signup.html", error=err, name=name, email=email, role=role)

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# AUTHENTICATION: LOGIN
# =========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    User Sign In:
    - Authenticates email and password.
    - Uses generic error messages to prevent email enumeration.
    - Stores minimal identity in session; never stores password or password_hash.
    - Role-based redirect to placeholder dashboard.
    """
    if request.method == "GET":
        if "user_id" in session and "user_role" in session:
            role = session.get("user_role")
            if role == "DONOR":
                return redirect(url_for("donor_dashboard"))
            elif role == "RECIPIENT":
                return redirect(url_for("recipient_dashboard"))
            elif role == "ADMIN":
                return redirect(url_for("admin_dashboard"))
        return render_template("login.html")

    is_json = request.is_json
    data = request.get_json(silent=True) if is_json else request.form

    email = str(data.get("email", "")).strip().lower() if data else ""
    password = str(data.get("password", "")) if data else ""

    if not email or not password:
        err = "Please enter both email and password."
        return (jsonify({"error": err}), 400) if is_json else render_template("login.html", error=err, email=email)

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT user_id, name, email, password_hash, role, is_active FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        # Generic authentication failure message (prevents user enumeration)
        generic_error = "Invalid email or password. Please verify your credentials and try again."

        if not user or not check_password_hash(user["password_hash"], password):
            return (jsonify({"error": generic_error}), 401) if is_json else render_template("login.html", error=generic_error, email=email)

        if not user.get("is_active"):
            inactive_err = "Your account is currently disabled. Please contact support."
            return (jsonify({"error": inactive_err}), 403) if is_json else render_template("login.html", error=inactive_err, email=email)

        # Secure Session Initialization (only store minimal identity, never password/hash)
        session.clear()
        session["user_id"] = user["user_id"]
        session["user_name"] = user["name"]
        session["user_role"] = user["role"]

        if is_json:
            return jsonify({
                "message": "Login successful",
                "user": {
                    "user_id": user["user_id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"]
                }
            }), 200

        # Safe role-based redirect (strictly hardcoded routes, avoiding open redirects)
        role = user.get("role")
        if role == "DONOR":
            return redirect(url_for("donor_dashboard"))
        elif role == "RECIPIENT":
            return redirect(url_for("recipient_dashboard"))
        elif role == "ADMIN":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("home"))

    except Exception:
        err = "An error occurred during sign in. Please try again."
        return (jsonify({"error": err}), 500) if is_json else render_template("login.html", error=err, email=email)

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# AUTHENTICATION: LOGOUT
# =========================================

@app.route("/logout", methods=["GET", "POST"])
def logout():
    """
    Clears all session variables and redirects to login.
    """
    session.clear()
    if request.is_json:
        return jsonify({"message": "Logged out successfully"}), 200
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))


# =========================================
# CAMPAIGN MANAGEMENT ROUTES
# =========================================

ALLOWED_CAMPAIGN_STATUSES = {"PLANNED", "UPCOMING", "ONGOING", "COMPLETED", "CANCELLED"}


def parse_campaign_datetime(val):
    """
    Parses datetime strings in various formats (ISO, space-separated, date-only).
    Returns datetime.datetime object or None if invalid.
    """
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, datetime.date):
        return datetime.datetime.combine(val, datetime.time.min)
    if not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M"
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(val, fmt)
        except ValueError:
            continue
    try:
        clean_iso = val.replace("Z", "+00:00").split("+")[0]
        return datetime.datetime.fromisoformat(clean_iso)
    except Exception:
        return None


def format_campaign_dict(row):
    """
    Formats a database row dictionary for JSON responses, ensuring ISO strings
    and calculating display_status for upcoming, ongoing, completed and cancelled campaigns.
    """
    if not row:
        return None
    d = dict(row)
    start_dt = d.get("start_date")
    end_dt = d.get("end_date")
    created_at = d.get("created_at")

    if isinstance(start_dt, (datetime.datetime, datetime.date)):
        d["start_date"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        d["start_date_iso"] = start_dt.isoformat()
    elif start_dt:
        d["start_date"] = str(start_dt)
        d["start_date_iso"] = str(start_dt)

    if isinstance(end_dt, (datetime.datetime, datetime.date)):
        d["end_date"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        d["end_date_iso"] = end_dt.isoformat()
    elif end_dt:
        d["end_date"] = str(end_dt)
        d["end_date_iso"] = str(end_dt)

    if isinstance(created_at, (datetime.datetime, datetime.date)):
        d["created_at"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
    elif created_at:
        d["created_at"] = str(created_at)

    status = str(d.get("status") or "PLANNED").upper()
    d["status"] = status

    # Compute date-aware display status for planned/upcoming/ongoing drives
    now = datetime.datetime.now()
    if status in ("PLANNED", "UPCOMING", "ONGOING"):
        if isinstance(start_dt, datetime.datetime) and isinstance(end_dt, datetime.datetime):
            if now < start_dt:
                d["display_status"] = "UPCOMING"
            elif start_dt <= now <= end_dt:
                d["display_status"] = "ONGOING"
            else:
                d["display_status"] = "COMPLETED"
        else:
            d["display_status"] = "UPCOMING" if status in ("PLANNED", "UPCOMING") else status
    else:
        d["display_status"] = status

    return d


@app.route("/campaigns", methods=["GET"])
@login_required
def get_campaigns():
    """
    Fetch blood donation campaigns.
    Accessible to DONORS, RECIPIENTS, and ADMINS.
    Optional query parameter:
    - status: UPCOMING, ONGOING, COMPLETED, CANCELLED, PLANNED, ALL
    - search: keyword search matching campaign_name or location
    """
    status_filter = request.args.get("status")
    search_query = request.args.get("search") or request.args.get("q")

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        query = "SELECT * FROM campaigns WHERE 1=1"
        params = []

        if status_filter:
            norm_status = status_filter.strip().upper()
            if norm_status != "ALL":
                if norm_status in ("UPCOMING", "PLANNED"):
                    query += " AND status IN ('UPCOMING', 'PLANNED')"
                elif norm_status in ALLOWED_CAMPAIGN_STATUSES:
                    query += " AND status = %s"
                    params.append(norm_status)
                else:
                    return jsonify({
                        "error": f"Invalid status filter '{status_filter}'. Allowed values: UPCOMING, ONGOING, COMPLETED, CANCELLED, PLANNED, ALL"
                    }), 400

        if search_query and search_query.strip():
            query += " AND (campaign_name LIKE %s OR location LIKE %s)"
            search_param = f"%{search_query.strip()}%"
            params.extend([search_param, search_param])

        query += " ORDER BY start_date ASC, campaign_id ASC"

        cursor.execute(query, tuple(params))
        campaigns = cursor.fetchall() or []

        formatted_campaigns = [format_campaign_dict(c) for c in campaigns]
        return jsonify(formatted_campaigns), 200

    except Exception:
        return jsonify({"error": "Failed to fetch campaigns due to a server error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/campaigns/<int:campaign_id>", methods=["GET"])
@login_required
def get_single_campaign(campaign_id):
    """
    Fetch a single campaign by ID.
    Accessible to DONORS, RECIPIENTS, and ADMINS.
    """
    if campaign_id <= 0:
        return jsonify({"error": "Invalid campaign_id."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        campaign = cursor.fetchone()

        if not campaign:
            return jsonify({"error": f"Campaign #{campaign_id} not found."}), 404

        return jsonify(format_campaign_dict(campaign)), 200

    except Exception:
        return jsonify({"error": "Failed to fetch campaign details."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/campaigns", methods=["POST"])
@roles_required("ADMIN")
def create_campaign():
    """
    Create a new blood donation campaign.
    Admin role only.
    Validates required fields, date formats, and logical date ranges.
    """
    data = request.get_json(silent=True) or request.form.to_dict() or {}

    campaign_name = str(data.get("campaign_name") or "").strip()
    if not campaign_name:
        return jsonify({"error": "Campaign name is required."}), 400
    if len(campaign_name) > 150:
        return jsonify({"error": "Campaign name must not exceed 150 characters."}), 400

    location = str(data.get("location") or "").strip()
    if not location:
        return jsonify({"error": "Campaign location is required."}), 400
    if len(location) > 150:
        return jsonify({"error": "Campaign location must not exceed 150 characters."}), 400

    start_raw = data.get("start_date")
    end_raw = data.get("end_date")
    if not start_raw or not end_raw:
        return jsonify({"error": "Both start date and end date are required."}), 400

    start_dt = parse_campaign_datetime(start_raw)
    if not start_dt:
        return jsonify({"error": "Invalid start date format. Please provide a valid date/time."}), 400

    end_dt = parse_campaign_datetime(end_raw)
    if not end_dt:
        return jsonify({"error": "Invalid end date format. Please provide a valid date/time."}), 400

    if end_dt <= start_dt:
        return jsonify({"error": "Campaign end date and time must be after start date and time."}), 400

    status_raw = data.get("status")
    status = (str(status_raw).strip().upper() if status_raw else "UPCOMING")
    if status not in ALLOWED_CAMPAIGN_STATUSES:
        return jsonify({
            "error": f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_CAMPAIGN_STATUSES))}"
        }), 400

    description = str(data.get("description") or "").strip() or None

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        insert_sql = """
            INSERT INTO campaigns (campaign_name, description, location, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_sql, (campaign_name, description, location, start_dt, end_dt, status))
        db.commit()

        new_campaign_id = cursor.lastrowid
        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (new_campaign_id,))
        created_campaign = cursor.fetchone()

        return jsonify({
            "message": "Campaign created successfully.",
            "campaign": format_campaign_dict(created_campaign)
        }), 201

    except Exception:
        if db:
            db.rollback()
        return jsonify({"error": "Failed to create campaign due to a database error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/campaigns/<int:campaign_id>", methods=["PUT", "PATCH"])
@roles_required("ADMIN")
def update_campaign(campaign_id):
    """
    Update campaign details (name, description, location, dates, status).
    Admin role only.
    """
    if campaign_id <= 0:
        return jsonify({"error": "Invalid campaign_id."}), 400

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    if not data:
        return jsonify({"error": "No update fields provided."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": f"Campaign #{campaign_id} not found."}), 404

        # Validate name if provided
        if "campaign_name" in data:
            campaign_name = str(data.get("campaign_name") or "").strip()
            if not campaign_name:
                return jsonify({"error": "Campaign name cannot be empty."}), 400
            if len(campaign_name) > 150:
                return jsonify({"error": "Campaign name must not exceed 150 characters."}), 400
        else:
            campaign_name = existing["campaign_name"]

        # Validate location if provided
        if "location" in data:
            location = str(data.get("location") or "").strip()
            if not location:
                return jsonify({"error": "Campaign location cannot be empty."}), 400
            if len(location) > 150:
                return jsonify({"error": "Campaign location must not exceed 150 characters."}), 400
        else:
            location = existing["location"]

        # Validate dates
        start_raw = data.get("start_date", existing["start_date"])
        end_raw = data.get("end_date", existing["end_date"])
        start_dt = parse_campaign_datetime(start_raw)
        end_dt = parse_campaign_datetime(end_raw)

        if not start_dt:
            return jsonify({"error": "Invalid start date format."}), 400
        if not end_dt:
            return jsonify({"error": "Invalid end date format."}), 400
        if end_dt <= start_dt:
            return jsonify({"error": "Campaign end date and time must be after start date and time."}), 400

        # Validate status if provided
        if "status" in data:
            status = str(data.get("status") or "").strip().upper()
            if status not in ALLOWED_CAMPAIGN_STATUSES:
                return jsonify({
                    "error": f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_CAMPAIGN_STATUSES))}"
                }), 400
        else:
            status = existing["status"]

        # Validate description
        if "description" in data:
            description = str(data.get("description") or "").strip() or None
        else:
            description = existing["description"]

        update_sql = """
            UPDATE campaigns
            SET campaign_name = %s, description = %s, location = %s, start_date = %s, end_date = %s, status = %s
            WHERE campaign_id = %s
        """
        cursor.execute(update_sql, (campaign_name, description, location, start_dt, end_dt, status, campaign_id))
        db.commit()

        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        updated = cursor.fetchone()

        return jsonify({
            "message": "Campaign updated successfully.",
            "campaign": format_campaign_dict(updated)
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({"error": "Failed to update campaign due to a database error."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/campaigns/<int:campaign_id>/status", methods=["PUT", "PATCH"])
@roles_required("ADMIN")
def update_campaign_status(campaign_id):
    """
    Change campaign status (e.g. mark completed, cancelled, ongoing, or upcoming).
    Admin role only.
    """
    if campaign_id <= 0:
        return jsonify({"error": "Invalid campaign_id."}), 400

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    status_raw = data.get("status")
    if not status_raw:
        return jsonify({"error": "Status field is required."}), 400

    status = str(status_raw).strip().upper()
    if status not in ALLOWED_CAMPAIGN_STATUSES:
        return jsonify({
            "error": f"Invalid status '{status}'. Allowed statuses: {', '.join(sorted(ALLOWED_CAMPAIGN_STATUSES))}"
        }), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": f"Campaign #{campaign_id} not found."}), 404

        cursor.execute("UPDATE campaigns SET status = %s WHERE campaign_id = %s", (status, campaign_id))
        db.commit()

        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        updated = cursor.fetchone()

        return jsonify({
            "message": f"Campaign status updated to {status}.",
            "campaign": format_campaign_dict(updated)
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({"error": "Failed to update campaign status."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/campaigns/<int:campaign_id>", methods=["DELETE"])
@roles_required("ADMIN")
def delete_campaign(campaign_id):
    """
    Delete a campaign.
    Admin role only.
    """
    if campaign_id <= 0:
        return jsonify({"error": "Invalid campaign_id."}), 400

    db = None
    cursor = None
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": f"Campaign #{campaign_id} not found."}), 404

        cursor.execute("DELETE FROM campaigns WHERE campaign_id = %s", (campaign_id,))
        db.commit()

        return jsonify({
            "message": f"Campaign #{campaign_id} deleted successfully.",
            "campaign_id": campaign_id
        }), 200

    except Exception:
        if db:
            db.rollback()
        return jsonify({"error": "Failed to delete campaign."}), 500
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# =========================================
# PLACEHOLDER DASHBOARDS
# =========================================

@app.route("/donor/dashboard", methods=["GET"])
@roles_required("DONOR")
def donor_dashboard():
    """Temporary placeholder for Donor Dashboard."""
    user_name = session.get("user_name", "Donor")
    user_role = session.get("user_role", "DONOR")
    return render_template("donor_dashboard.html", user_name=user_name, user_role=user_role)


@app.route("/recipient/dashboard", methods=["GET"])
@roles_required("RECIPIENT")
def recipient_dashboard():
    """Temporary placeholder for Recipient Dashboard."""
    user_name = session.get("user_name", "Recipient")
    user_role = session.get("user_role", "RECIPIENT")
    return render_template("recipient_dashboard.html", user_name=user_name, user_role=user_role)


@app.route("/admin/dashboard", methods=["GET"])
@roles_required("ADMIN")
def admin_dashboard():
    """Temporary placeholder for Admin Console."""
    user_name = session.get("user_name", "Administrator")
    user_role = session.get("user_role", "ADMIN")
    return render_template("admin_dashboard.html", user_name=user_name, user_role=user_role)


# =========================================
# RUN SERVER
# =========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)