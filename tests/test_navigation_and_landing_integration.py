"""
Navigation and Landing-Page Integration Test Suite
--------------------------------------------------
Validates:
1. Role-based navigation rendering in templates/index.html:
   - Unauthenticated: Home, Login, Signup, Platform Stats (#dashboard-overview), Emergency Board (#emergency-requests).
   - Donor: Home, My Dashboard (/donor/dashboard), Logout (/logout), DONOR role indicator.
   - Recipient: Home, My Dashboard (/recipient/dashboard), Logout (/logout), RECIPIENT role indicator.
   - Admin: Home, Admin Dashboard (/admin/dashboard), Logout (/logout), ADMIN role indicator.
2. Dashboard navbar link points to the role-specific dashboard instead of merely scrolling to #dashboard-overview.
3. Hero action button role routing:
   - Unauthenticated: Find Blood Donors -> /login, Emergency Blood Request -> /login.
   - Recipient: Find Blood Donors -> /recipient/dashboard#section-search-donors, Emergency Blood Request -> /recipient/dashboard#section-create-emergency.
   - Donor: Find Blood Donors -> /donor/dashboard.
   - Admin: Find Blood Donors -> /admin/dashboard.
4. Obsolete management sections (#donor-management, #recipient-directory) are hidden from display.
5. Home -> My Dashboard navigation and session clearing on logout.
6. Real-database functional tests using disposable donor and recipient accounts, verifying role redirects and cross-role access protection, with strictly clean teardown.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
from app import app
from database import get_db_connection


class TestRoleBasedNavigationMarkup(unittest.TestCase):
    """Verifies navbar and hero action button markup for all user roles."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # 1. Unauthenticated Visitor
    def test_unauthenticated_navigation_and_hero(self):
        """Unauthenticated visitor sees Home, Login, Signup, public info links, and login-directed hero buttons."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Public nav links
        self.assertIn('id="nav-link-home"', html)
        self.assertIn('href="/login"', html)
        self.assertIn('id="nav-link-login"', html)
        self.assertIn('href="/signup"', html)
        self.assertIn('id="nav-link-signup"', html)
        self.assertIn('href="#dashboard-overview"', html)
        self.assertIn('id="nav-link-overview"', html)

        # Should NOT contain authenticated links in active navbar
        self.assertNotIn('id="nav-link-dashboard"', html)
        self.assertNotIn('id="nav-link-logout"', html)

        # Hero buttons direct unauthenticated visitors to login
        self.assertIn('id="cta-find-donors"', html)
        self.assertIn('id="cta-emergency"', html)
        self.assertIn('href="/login" class="btn btn-primary" id="cta-find-donors"', html)
        self.assertIn('href="/login" class="btn btn-secondary" id="cta-emergency"', html)

        # Obsolete management sections are hidden
        self.assertIn('id="donor-management" style="display: none;"', html)
        self.assertIn('id="recipient-directory" style="display: none;"', html)

    # 2. Authenticated Donor
    def test_donor_navigation_and_hero(self):
        """Authenticated DONOR sees Home, My Dashboard (/donor/dashboard), Logout, and role tag."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Donor"
            sess["user_role"] = "DONOR"

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Donor role navigation
        self.assertIn('href="/" id="nav-link-home"', html)
        self.assertIn('href="/donor/dashboard" id="nav-link-dashboard"', html)
        self.assertIn('My Dashboard', html)
        self.assertIn('href="/logout" class="nav-auth-link" id="nav-link-logout"', html)
        self.assertIn('DONOR', html)

        # Public auth links not shown in navbar
        self.assertNotIn('id="nav-link-login"', html)
        self.assertNotIn('id="nav-link-signup"', html)

        # Hero button directs to donor dashboard
        self.assertIn('href="/donor/dashboard" class="btn btn-primary" id="cta-find-donors"', html)

    # 3. Authenticated Recipient
    def test_recipient_navigation_and_hero(self):
        """Authenticated RECIPIENT sees Home, My Dashboard (/recipient/dashboard), Logout, and recipient-directed hero buttons."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Recipient"
            sess["user_role"] = "RECIPIENT"

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Recipient role navigation
        self.assertIn('href="/" id="nav-link-home"', html)
        self.assertIn('href="/recipient/dashboard" id="nav-link-dashboard"', html)
        self.assertIn('My Dashboard', html)
        self.assertIn('href="/logout" class="nav-auth-link" id="nav-link-logout"', html)
        self.assertIn('RECIPIENT', html)

        # Public auth links not shown
        self.assertNotIn('id="nav-link-login"', html)
        self.assertNotIn('id="nav-link-signup"', html)

        # Hero buttons direct recipient to specific dashboard functional sections
        self.assertIn('href="/recipient/dashboard#section-search-donors" class="btn btn-primary" id="cta-find-donors"', html)
        self.assertIn('href="/recipient/dashboard#section-create-emergency" class="btn btn-secondary" id="cta-emergency"', html)

    # 4. Authenticated Admin
    def test_admin_navigation_and_hero(self):
        """Authenticated ADMIN sees Home, Admin Dashboard (/admin/dashboard), Logout, and ADMIN role indicator."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 303
            sess["user_name"] = "System Admin"
            sess["user_role"] = "ADMIN"

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Admin role navigation
        self.assertIn('href="/" id="nav-link-home"', html)
        self.assertIn('href="/admin/dashboard" id="nav-link-dashboard"', html)
        self.assertIn('Admin Dashboard', html)
        self.assertIn('href="/logout" class="nav-auth-link" id="nav-link-logout"', html)
        self.assertIn('ADMIN', html)

        # Hero buttons direct admin to admin dashboard
        self.assertIn('href="/admin/dashboard" class="btn btn-primary" id="cta-find-donors"', html)

    # 5. Home and then My Dashboard round-trip verification
    def test_donor_home_to_dashboard_roundtrip(self):
        """Donor can navigate from /donor/dashboard to / (Home) and back to /donor/dashboard."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        # 1. Access Donor Dashboard
        res_dash = self.client.get("/donor/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn('id="nav-link-home"', res_dash.get_data(as_text=True))

        # 2. Click Home (navigate to /)
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        home_html = res_home.get_data(as_text=True)
        self.assertIn('href="/donor/dashboard" id="nav-link-dashboard"', home_html)

        # 3. Click My Dashboard from Home
        res_dash_return = self.client.get("/donor/dashboard")
        self.assertEqual(res_dash_return.status_code, 200)
        self.assertIn("Donor Portal", res_dash_return.get_data(as_text=True))

    def test_recipient_home_to_dashboard_roundtrip(self):
        """Recipient can navigate from /recipient/dashboard to / (Home) and back to /recipient/dashboard."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        # 1. Access Recipient Dashboard
        res_dash = self.client.get("/recipient/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn('id="nav-link-home"', res_dash.get_data(as_text=True))

        # 2. Click Home (navigate to /)
        res_home = self.client.get("/")
        self.assertEqual(res_home.status_code, 200)
        home_html = res_home.get_data(as_text=True)
        self.assertIn('href="/recipient/dashboard" id="nav-link-dashboard"', home_html)

        # 3. Click My Dashboard from Home
        res_dash_return = self.client.get("/recipient/dashboard")
        self.assertEqual(res_dash_return.status_code, 200)
        self.assertIn("Recipient Portal", res_dash_return.get_data(as_text=True))

    # 6. Logout session clearance verification
    def test_logout_clears_session_and_restores_unauthenticated_nav(self):
        """Logging out clears session variables and restores unauthenticated landing navigation."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        # Verify logged-in state on home
        res_before = self.client.get("/")
        self.assertIn('id="nav-link-dashboard"', res_before.get_data(as_text=True))

        # Perform logout
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)
        self.assertIn("/login", logout_res.headers.get("Location", ""))

        # Verify session is empty
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
            self.assertNotIn("user_role", sess)

        # Verify home page renders unauthenticated view
        res_after = self.client.get("/")
        after_html = res_after.get_data(as_text=True)
        self.assertIn('id="nav-link-login"', after_html)
        self.assertNotIn('id="nav-link-dashboard"', after_html)


class TestRealDatabaseNavigationLifecycle(unittest.TestCase):
    """
    End-to-end integration test with live MySQL database:
    - Registers disposable DONOR and RECIPIENT accounts.
    - Tests login, role-specific redirection, landing navigation, cross-role protection.
    - Cleans up exclusively created test accounts without altering demo records.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app.config["TESTING"] = True
        cls.donor_email = "disposable_donor_test_nav@example.com"
        cls.recipient_email = "disposable_recip_test_nav@example.com"
        cls.password = "TestPassword@123"

        # Record pre-test counts
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM donors")
        cls.initial_donors_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM recipients")
        cls.initial_recipients_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM emergency_requests")
        cls.initial_emergency_count = cursor.fetchone()[0]
        cursor.close()
        db.close()

    @classmethod
    def tearDownClass(cls):
        # Strictly clean up only the disposable test accounts
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("DELETE FROM users WHERE email IN (%s, %s)", (cls.donor_email, cls.recipient_email))
        db.commit()

        # Validate that demo records were NOT modified
        cursor.execute("SELECT COUNT(*) FROM donors")
        final_donors = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM recipients")
        final_recipients = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM emergency_requests")
        final_emergency = cursor.fetchone()[0]
        cursor.close()
        db.close()

        assert final_donors == cls.initial_donors_count, "Demo donors table was modified!"
        assert final_recipients == cls.initial_recipients_count, "Demo recipients table was modified!"
        assert final_emergency == cls.initial_emergency_count, "Demo emergency_requests table was modified!"

    def setUp(self):
        self.client = self.app.test_client()

    def test_disposable_donor_full_navigation_lifecycle(self):
        """Test signup, login, navigation, cross-role access protection, and logout for a DONOR."""
        # 1. Sign up disposable donor (redirects to /login)
        signup_res = self.client.post("/signup", data={
            "name": "Disposable Donor",
            "email": self.donor_email,
            "password": self.password,
            "confirm_password": self.password,
            "role": "DONOR"
        })
        self.assertEqual(signup_res.status_code, 302)
        self.assertIn("/login", signup_res.headers.get("Location", ""))

        # 2. Login as donor (redirects to /donor/dashboard)
        login_res = self.client.post("/login", data={
            "email": self.donor_email,
            "password": self.password
        })
        self.assertEqual(login_res.status_code, 302)
        self.assertIn("/donor/dashboard", login_res.headers.get("Location", ""))

        # 3. Access / (Home) as authenticated donor
        home_res = self.client.get("/")
        self.assertEqual(home_res.status_code, 200)
        home_html = home_res.get_data(as_text=True)
        self.assertIn('href="/donor/dashboard" id="nav-link-dashboard"', home_html)
        self.assertIn('DONOR', home_html)

        # 4. Click My Dashboard -> loads donor dashboard
        dash_res = self.client.get("/donor/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn("Donor Portal", dash_res.get_data(as_text=True))

        # 5. Cross-role protection: Donor cannot access recipient or admin routes
        recip_dash_res = self.client.get("/recipient/dashboard")
        self.assertEqual(recip_dash_res.status_code, 403)

        admin_dash_res = self.client.get("/admin/dashboard")
        self.assertEqual(admin_dash_res.status_code, 403)

        # 6. Logout
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)

        # 7. Verify unauthenticated state after logout
        post_logout_res = self.client.get("/")
        self.assertIn('id="nav-link-login"', post_logout_res.get_data(as_text=True))
        self.assertNotIn('id="nav-link-dashboard"', post_logout_res.get_data(as_text=True))

    def test_disposable_recipient_full_navigation_lifecycle(self):
        """Test signup, login, navigation, cross-role access protection, and logout for a RECIPIENT."""
        # 1. Sign up disposable recipient (redirects to /login)
        signup_res = self.client.post("/signup", data={
            "name": "Disposable Recipient",
            "email": self.recipient_email,
            "password": self.password,
            "confirm_password": self.password,
            "role": "RECIPIENT"
        })
        self.assertEqual(signup_res.status_code, 302)
        self.assertIn("/login", signup_res.headers.get("Location", ""))

        # 2. Login as recipient (redirects to /recipient/dashboard)
        login_res = self.client.post("/login", data={
            "email": self.recipient_email,
            "password": self.password
        })
        self.assertEqual(login_res.status_code, 302)
        self.assertIn("/recipient/dashboard", login_res.headers.get("Location", ""))

        # 3. Access / (Home) as authenticated recipient
        home_res = self.client.get("/")
        self.assertEqual(home_res.status_code, 200)
        home_html = home_res.get_data(as_text=True)
        self.assertIn('href="/recipient/dashboard" id="nav-link-dashboard"', home_html)
        self.assertIn('RECIPIENT', home_html)

        # Hero buttons route directly to functional sections of recipient dashboard
        self.assertIn('href="/recipient/dashboard#section-search-donors"', home_html)
        self.assertIn('href="/recipient/dashboard#section-create-emergency"', home_html)

        # 4. Click My Dashboard -> loads recipient dashboard
        dash_res = self.client.get("/recipient/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn("Recipient Portal", dash_res.get_data(as_text=True))

        # 5. Cross-role protection: Recipient cannot access donor or admin routes
        donor_dash_res = self.client.get("/donor/dashboard")
        self.assertEqual(donor_dash_res.status_code, 403)

        admin_dash_res = self.client.get("/admin/dashboard")
        self.assertEqual(admin_dash_res.status_code, 403)

        # 6. Logout
        logout_res = self.client.get("/logout")
        self.assertEqual(logout_res.status_code, 302)

        # 7. Verify unauthenticated state after logout
        post_logout_res = self.client.get("/")
        self.assertIn('id="nav-link-login"', post_logout_res.get_data(as_text=True))
        self.assertNotIn('id="nav-link-dashboard"', post_logout_res.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
