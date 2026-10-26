"""
Unit and Integration Tests for BloodLink Authentication (Stage 1)
-----------------------------------------------------------------
Covers:
- Signup (DONOR and RECIPIENT registration, required fields, validation)
- Prevention of public ADMIN account creation
- Password hashing with Werkzeug (never plaintext)
- Duplicate email handling with friendly error messaging
- Login with password hash verification
- Generic error messages (preventing email enumeration)
- Inactive account rejection
- Session security (HttpOnly, SameSite, minimal identity storage, no passwords in session)
- Logout and session clearing
- Placeholder dashboard rendering

Uses Flask test_client and unittest.mock to ensure the active MySQL database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
from werkzeug.security import generate_password_hash, check_password_hash

from app import app


class TestSignup(unittest.TestCase):
    """Tests for POST /signup (User Registration)"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.get_db_connection")
    def test_signup_donor_success_form(self, mock_get_db):
        """Test successfully registering a voluntary DONOR via HTML form submission"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock email check (no duplicate exists)
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 1

        payload = {
            "name": "Aarav Patel",
            "email": "aarav.patel@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
            "role": "DONOR"
        }

        response = self.client.post("/signup", data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        # Verify SQL execution
        mock_cursor.execute.assert_any_call(
            "SELECT user_id FROM users WHERE email = %s",
            ("aarav.patel@example.com",)
        )
        mock_db.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_signup_recipient_success_json(self, mock_get_db):
        """Test successfully registering a RECIPIENT via JSON API request"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 2

        payload = {
            "name": "Pooja Sharma",
            "email": "pooja.sharma@example.com",
            "password": "Password987654!",
            "confirm_password": "Password987654!",
            "role": "RECIPIENT"
        }

        response = self.client.post(
            "/signup",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["user_id"], 2)
        self.assertEqual(data["role"], "RECIPIENT")
        self.assertIn("registered successfully", data["message"].lower())
        mock_db.commit.assert_called_once()

    def test_signup_reject_public_admin(self):
        """Test that public registration as ADMIN is strictly disallowed"""
        payload = {
            "name": "Malicious Admin",
            "email": "admin@example.com",
            "password": "AdminPassword123!",
            "confirm_password": "AdminPassword123!",
            "role": "ADMIN"
        }

        response = self.client.post(
            "/signup",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("only available for donors and recipients", data["error"].lower())

    def test_signup_reject_arbitrary_role(self):
        """Test that unknown or arbitrary roles are rejected"""
        payload = {
            "name": "Hacker",
            "email": "hacker@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": "SUPERUSER"
        }

        response = self.client.post(
            "/signup",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)

    def test_signup_reject_missing_fields(self):
        """Test rejection when required fields are missing"""
        # Missing name
        res = self.client.post("/signup", json={"email": "a@b.com", "password": "Password123", "confirm_password": "Password123", "role": "DONOR"})
        self.assertEqual(res.status_code, 400)

        # Missing email
        res = self.client.post("/signup", json={"name": "Bob", "password": "Password123", "confirm_password": "Password123", "role": "DONOR"})
        self.assertEqual(res.status_code, 400)

        # Missing password
        res = self.client.post("/signup", json={"name": "Bob", "email": "a@b.com", "confirm_password": "Password123", "role": "DONOR"})
        self.assertEqual(res.status_code, 400)

        # Missing role
        res = self.client.post("/signup", json={"name": "Bob", "email": "a@b.com", "password": "Password123", "confirm_password": "Password123"})
        self.assertEqual(res.status_code, 400)

    def test_signup_reject_invalid_email(self):
        """Test rejection when email format is invalid"""
        res = self.client.post("/signup", json={
            "name": "Bob",
            "email": "not-an-email",
            "password": "Password123",
            "confirm_password": "Password123",
            "role": "DONOR"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("valid email", res.get_json()["error"].lower())

    def test_signup_reject_short_password(self):
        """Test rejection when password is less than 8 characters"""
        res = self.client.post("/signup", json={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "short",
            "confirm_password": "short",
            "role": "DONOR"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("8 characters", res.get_json()["error"].lower())

    def test_signup_reject_password_mismatch(self):
        """Test rejection when password and confirm_password do not match"""
        res = self.client.post("/signup", json={
            "name": "Bob",
            "email": "bob@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPassword456!",
            "role": "DONOR"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("passwords do not match", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_signup_reject_duplicate_email(self, mock_get_db):
        """Test friendly rejection when email is already registered"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock existing user found
        mock_cursor.fetchone.return_value = {"user_id": 42}

        res = self.client.post("/signup", json={
            "name": "Duplicate User",
            "email": "existing@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": "DONOR"
        })
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_signup_password_never_stored_as_plaintext(self, mock_get_db):
        """Test that the password passed to MySQL is securely hashed, never plaintext"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 10

        raw_password = "MySuperSecretPlaintextPassword123!"

        res = self.client.post("/signup", json={
            "name": "Security Tester",
            "email": "security@example.com",
            "password": raw_password,
            "confirm_password": raw_password,
            "role": "DONOR"
        })
        self.assertEqual(res.status_code, 201)

        # Inspect the arguments passed to cursor.execute for INSERT
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if "INSERT INTO users" in str(c)
        ]
        self.assertEqual(len(insert_calls), 1)

        call_args, _ = insert_calls[0]
        params = call_args[1]  # (name, email, password_hash, role)
        stored_hash = params[2]

        # Assert plaintext password was NEVER passed to SQL
        self.assertNotEqual(stored_hash, raw_password)
        # Assert stored value is indeed a valid Werkzeug hash verifying against raw password
        self.assertTrue(check_password_hash(stored_hash, raw_password))


class TestLogin(unittest.TestCase):
    """Tests for POST /login and authentication session management"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.get_db_connection")
    def test_login_donor_success(self, mock_get_db):
        """Test successful DONOR login: sets session and redirects to donor dashboard"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("ValidDonorPassword123!")
        mock_cursor.fetchone.return_value = {
            "user_id": 10,
            "name": "Kavita Verma",
            "email": "kavita@example.com",
            "password_hash": hashed,
            "role": "DONOR",
            "is_active": 1
        }

        response = self.client.post("/login", data={
            "email": "kavita@example.com",
            "password": "ValidDonorPassword123!"
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("/donor/dashboard", response.headers["Location"])

        # Check session
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_id"), 10)
            self.assertEqual(sess.get("user_name"), "Kavita Verma")
            self.assertEqual(sess.get("user_role"), "DONOR")
            # Crucial: verify passwords or hashes are never in session
            self.assertNotIn("password", sess)
            self.assertNotIn("password_hash", sess)

    @patch("app.get_db_connection")
    def test_login_recipient_success(self, mock_get_db):
        """Test successful RECIPIENT login: redirects to recipient dashboard"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("RecipientPass123!")
        mock_cursor.fetchone.return_value = {
            "user_id": 20,
            "name": "Rohan Joshi",
            "email": "rohan@example.com",
            "password_hash": hashed,
            "role": "RECIPIENT",
            "is_active": 1
        }

        response = self.client.post("/login", data={
            "email": "rohan@example.com",
            "password": "RecipientPass123!"
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("/recipient/dashboard", response.headers["Location"])

    @patch("app.get_db_connection")
    def test_login_admin_success(self, mock_get_db):
        """Test successful ADMIN login (pre-existing admin account): redirects to admin dashboard"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("AdminPass999!")
        mock_cursor.fetchone.return_value = {
            "user_id": 99,
            "name": "System Administrator",
            "email": "sysadmin@bloodlink.org",
            "password_hash": hashed,
            "role": "ADMIN",
            "is_active": 1
        }

        response = self.client.post("/login", data={
            "email": "sysadmin@bloodlink.org",
            "password": "AdminPass999!"
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/dashboard", response.headers["Location"])

    @patch("app.get_db_connection")
    def test_login_json_success(self, mock_get_db):
        """Test login via JSON API request returns user details without password"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("Pass123456!")
        mock_cursor.fetchone.return_value = {
            "user_id": 15,
            "name": "Meera Sen",
            "email": "meera@example.com",
            "password_hash": hashed,
            "role": "DONOR",
            "is_active": 1
        }

        response = self.client.post(
            "/login",
            json={"email": "meera@example.com", "password": "Pass123456!"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user"]["user_id"], 15)
        self.assertEqual(data["user"]["role"], "DONOR")
        self.assertNotIn("password", data["user"])
        self.assertNotIn("password_hash", data["user"])

    @patch("app.get_db_connection")
    def test_login_failure_wrong_password(self, mock_get_db):
        """Test login failure with wrong password returns generic error"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("CorrectPassword123!")
        mock_cursor.fetchone.return_value = {
            "user_id": 10,
            "name": "User",
            "email": "user@example.com",
            "password_hash": hashed,
            "role": "DONOR",
            "is_active": 1
        }

        response = self.client.post("/login", json={
            "email": "user@example.com",
            "password": "WrongPassword!"
        })
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("invalid email or password", data["error"].lower())

    @patch("app.get_db_connection")
    def test_login_failure_nonexistent_email(self, mock_get_db):
        """Test login failure with nonexistent email returns identical generic error (no enumeration)"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # No user in DB
        mock_cursor.fetchone.return_value = None

        response = self.client.post("/login", json={
            "email": "nonexistent@example.com",
            "password": "SomePassword123!"
        })
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("invalid email or password", data["error"].lower())

    @patch("app.get_db_connection")
    def test_login_failure_inactive_account(self, mock_get_db):
        """Test login rejection when is_active is 0"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        hashed = generate_password_hash("Password123!")
        mock_cursor.fetchone.return_value = {
            "user_id": 10,
            "name": "Disabled User",
            "email": "disabled@example.com",
            "password_hash": hashed,
            "role": "DONOR",
            "is_active": 0
        }

        response = self.client.post("/login", json={
            "email": "disabled@example.com",
            "password": "Password123!"
        })
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.get_json()["error"].lower())

    def test_login_missing_credentials(self):
        """Test rejection when email or password is missing"""
        res = self.client.post("/login", json={"email": "test@example.com"})
        self.assertEqual(res.status_code, 400)

        res = self.client.post("/login", json={"password": "password"})
        self.assertEqual(res.status_code, 400)


class TestLogout(unittest.TestCase):
    """Tests for /logout"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_logout_clears_session(self):
        """Test that /logout clears all session data and redirects to /login"""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 5
            sess["user_name"] = "Active User"
            sess["user_role"] = "DONOR"

        res = self.client.get("/logout")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

        # Check session is cleared
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
            self.assertNotIn("user_name", sess)
            self.assertNotIn("user_role", sess)

    def test_logout_json(self):
        """Test JSON logout request"""
        res = self.client.post("/logout", headers={"Content-Type": "application/json"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("logged out", res.get_json()["message"].lower())


class TestSecurityAndPages(unittest.TestCase):
    """Tests for security cookies and authentication page rendering"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_session_cookie_security_config(self):
        """Verify strict session cookie security settings"""
        self.assertTrue(self.app.config.get("SESSION_COOKIE_HTTPONLY"))
        self.assertEqual(self.app.config.get("SESSION_COOKIE_SAMESITE"), "Lax")

    def test_signup_page_renders_html(self):
        """Test GET /signup returns 200 with signup form elements"""
        res = self.client.get("/signup")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('id="signup-form"', html)
        self.assertIn('name="email"', html)
        self.assertIn('name="password"', html)
        self.assertIn('name="confirm_password"', html)
        self.assertIn('name="role"', html)
        self.assertIn('value="DONOR"', html)
        self.assertIn('value="RECIPIENT"', html)
        # ADMIN option should NOT be in the public dropdown
        self.assertNotIn('value="ADMIN"', html)

    def test_login_page_renders_html(self):
        """Test GET /login returns 200 with login form elements"""
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('id="login-form"', html)
        self.assertIn('name="email"', html)
        self.assertIn('name="password"', html)
        self.assertIn('href="/signup"', html)

    def test_placeholder_dashboards_render(self):
        """Test placeholder dashboard endpoints render properly"""
        with self.client.session_transaction() as sess:
            sess["user_name"] = "Test Donor"
            sess["user_role"] = "DONOR"
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Test Donor", res.get_data(as_text=True))

        with self.client.session_transaction() as sess:
            sess["user_name"] = "Test Recipient"
            sess["user_role"] = "RECIPIENT"
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Test Recipient", res.get_data(as_text=True))

        with self.client.session_transaction() as sess:
            sess["user_name"] = "Super Admin"
            sess["user_role"] = "ADMIN"
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Super Admin", res.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
