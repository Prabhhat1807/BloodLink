"""
Unit and Integration Tests for BloodLink Task 7:
Donor Management — Edit Details, Availability Management, and Search/Matching Integration.
Uses Flask test_client and unittest.mock to ensure the active database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime
from decimal import Decimal

from app import app
from matching import find_best_donors, is_compatible, bubble_sort


class TestDonorEditMocked(unittest.TestCase):
    """Tests for PUT /donors/<donor_id> and PATCH /donors/<donor_id>"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Rahul Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_update_donor_success(self, mock_get_db):
        """Test successfully updating donor details"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock existing donor lookup
        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "name": "Rahul Sharma",
            "age": 22,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune",
            "availability": 1,
            "last_donation_date": datetime.date(2026, 6, 15),
            "weight": Decimal("68.50"),
            "medical_status": "Healthy"
        }

        payload = {
            "name": "Rahul V. Sharma",
            "age": 23,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Kothrud, Pune",
            "availability": True,
            "last_donation_date": "2026-07-01",
            "weight": 70.0,
            "medical_status": "Fit and Healthy"
        }

        response = self.client.put(
            "/donors/1",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["donor_id"], 1)
        self.assertEqual(data["donor"]["name"], "Rahul V. Sharma")
        self.assertEqual(data["donor"]["age"], 23)
        self.assertEqual(data["donor"]["phone"], "9876543299")
        self.assertEqual(data["donor"]["location"], "Kothrud, Pune")
        self.assertEqual(data["donor"]["availability"], 1)

        # Verify SQL execution and commit
        mock_db.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_patch_partial_update(self, mock_get_db):
        """Test partial update via PATCH keeping unspecified existing fields"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 2,
            "name": "Aman Patil",
            "age": 24,
            "gender": "Male",
            "blood_group": "B+",
            "phone": "9876543211",
            "location": "Pimpri",
            "availability": 1,
            "last_donation_date": datetime.date(2026, 7, 10),
            "weight": Decimal("72.00"),
            "medical_status": "Healthy"
        }

        # Only updating phone and location
        payload = {
            "phone": "9998887776",
            "location": "Chinchwad, Pune"
        }

        response = self.client.patch(
            "/donors/2",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["donor"]["phone"], "9998887776")
        self.assertEqual(data["donor"]["location"], "Chinchwad, Pune")
        # Existing unedited fields preserved
        self.assertEqual(data["donor"]["name"], "Aman Patil")
        self.assertEqual(data["donor"]["blood_group"], "B+")
        self.assertEqual(data["donor"]["age"], 24)

    @patch("app.get_db_connection")
    def test_update_nonexistent_donor(self, mock_get_db):
        """Test 404 when updating a donor that does not exist"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None

        response = self.client.put(
            "/donors/99999",
            data=json.dumps({
                "name": "Nonexistent Donor",
                "age": 30,
                "blood_group": "O+",
                "phone": "9876543210",
                "location": "Pune"
            }),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"].lower())

    def test_update_invalid_id(self):
        """Test rejecting invalid donor_id <= 0"""
        response = self.client.put(
            "/donors/0",
            data=json.dumps({"name": "Test"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("app.get_db_connection")
    def test_update_validation_errors(self, mock_get_db):
        """Test input validations for donor updates (age, blood_group, phone, weight, name)"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1, "name": "Rahul", "age": 22, "blood_group": "O+",
            "phone": "9876543210", "location": "Pune", "availability": 1,
            "gender": "Male", "weight": Decimal("68.5"), "last_donation_date": None,
            "medical_status": "Healthy"
        }

        # 1. Invalid Age < 18
        res = self.client.put("/donors/1", json={"name": "Rahul", "age": 16, "blood_group": "O+", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("18 and 65", res.get_json()["error"])

        # 2. Invalid Age > 65
        res = self.client.put("/donors/1", json={"name": "Rahul", "age": 70, "blood_group": "O+", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

        # 3. Invalid Blood Group
        res = self.client.put("/donors/1", json={"name": "Rahul", "age": 25, "blood_group": "C+", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid blood group", res.get_json()["error"])

        # 4. Invalid Phone length
        res = self.client.put("/donors/1", json={"name": "Rahul", "age": 25, "blood_group": "O+", "phone": "123", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

        # 5. Invalid Name (too short)
        res = self.client.put("/donors/1", json={"name": "R", "age": 25, "blood_group": "O+", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

        # 6. Invalid Weight (< 40 kg)
        res = self.client.put("/donors/1", json={"name": "Rahul", "age": 25, "blood_group": "O+", "phone": "9876543210", "location": "Pune", "weight": 35})
        self.assertEqual(res.status_code, 400)

    @patch("app.get_db_connection")
    def test_update_db_error_triggers_rollback(self, mock_get_db):
        """Test rollback and 500 status on database failure"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1, "name": "Rahul", "age": 22, "blood_group": "O+",
            "phone": "9876543210", "location": "Pune", "availability": 1,
            "gender": "Male", "weight": Decimal("68.5"), "last_donation_date": None,
            "medical_status": "Healthy"
        }
        # Simulate execute error on update query
        mock_cursor.execute.side_effect = [None, Exception("Simulated DB failure")]

        res = self.client.put("/donors/1", json={
            "name": "Rahul Sharma", "age": 25, "blood_group": "O+", "phone": "9876543210", "location": "Pune"
        })
        self.assertEqual(res.status_code, 500)
        mock_db.rollback.assert_called_once()


class TestDonorAvailabilityMocked(unittest.TestCase):
    """Tests for PATCH /donors/<donor_id>/availability and PUT /donors/<donor_id>/availability"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Rahul Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_toggle_to_unavailable_success(self, mock_get_db):
        """Test marking an active donor as unavailable (0)"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "name": "Rahul Sharma",
            "availability": 1
        }

        response = self.client.patch(
            "/donors/1/availability",
            data=json.dumps({"availability": 0}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["donor_id"], 1)
        self.assertEqual(data["availability"], 0)
        self.assertEqual(data["previous_availability"], 1)
        self.assertIn("Unavailable", data["message"])

        mock_cursor.execute.assert_any_call(
            "UPDATE donors SET availability = %s WHERE donor_id = %s",
            (0, 1)
        )
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_toggle_to_available_success(self, mock_get_db):
        """Test marking an unavailable donor as available (1) using string 'available'"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 5,
            "name": "Rohan Deshmukh",
            "availability": 0
        }

        response = self.client.patch(
            "/donors/5/availability",
            data=json.dumps({"availability": "available"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["donor_id"], 5)
        self.assertEqual(data["availability"], 1)
        self.assertEqual(data["previous_availability"], 0)
        self.assertIn("Available", data["message"])

        mock_cursor.execute.assert_any_call(
            "UPDATE donors SET availability = %s WHERE donor_id = %s",
            (1, 5)
        )
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_toggle_boolean_value(self, mock_get_db):
        """Test passing boolean True/False for availability"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"donor_id": 3, "name": "Priya", "availability": 1}

        res = self.client.put(
            "/donors/3/availability",
            data=json.dumps({"availability": False}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["availability"], 0)

    def test_toggle_invalid_values(self):
        """Test rejecting invalid availability values"""
        # Missing field
        res = self.client.patch("/donors/1/availability", json={})
        self.assertEqual(res.status_code, 400)

        # Invalid string
        res = self.client.patch("/donors/1/availability", json={"availability": "maybe"})
        self.assertEqual(res.status_code, 400)

        # Invalid integer
        res = self.client.patch("/donors/1/availability", json={"availability": 99})
        self.assertEqual(res.status_code, 400)

        # Invalid ID <= 0
        res = self.client.patch("/donors/0/availability", json={"availability": 1})
        self.assertEqual(res.status_code, 400)

    @patch("app.get_db_connection")
    def test_toggle_nonexistent_donor(self, mock_get_db):
        """Test 404 when toggling availability for nonexistent donor"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None

        res = self.client.patch("/donors/99999/availability", json={"availability": 1})
        self.assertEqual(res.status_code, 404)


class TestAvailabilityMatchingIntegration(unittest.TestCase):
    """Test how donor availability directly controls matching and search results"""

    def test_unavailable_donors_excluded_from_matching(self):
        """Verify that find_best_donors strictly excludes donors with availability != 1"""
        donors = [
            {"donor_id": 1, "name": "Rahul", "blood_group": "O+", "location": "Pune", "availability": 1},
            {"donor_id": 2, "name": "Aman", "blood_group": "O+", "location": "Pune", "availability": 0},
            {"donor_id": 3, "name": "Priya", "blood_group": "O-", "location": "Pune", "availability": 1},
            {"donor_id": 4, "name": "Sneha", "blood_group": "O-", "location": "Pune", "availability": 0},
        ]

        # Recipient needing O+
        matched = find_best_donors(donors, "O+", "Pune")

        # Only donors with availability == 1 should be included
        matched_ids = [d["donor_id"] for d in matched]
        self.assertIn(1, matched_ids)
        self.assertIn(3, matched_ids)
        self.assertNotIn(2, matched_ids, "Donor 2 (availability=0) must be excluded from matches")
        self.assertNotIn(4, matched_ids, "Donor 4 (availability=0) must be excluded from matches")

    def test_availability_toggle_impact_on_matching(self):
        """Simulate toggling donor availability and verify dynamic search inclusion/exclusion"""
        donor_pool = [
            {"donor_id": 5, "name": "Rohan", "blood_group": "AB+", "location": "Wakad", "availability": 0}
        ]

        # Initially unavailable: 0 matches
        initial_matches = find_best_donors(donor_pool, "AB+", "Wakad")
        self.assertEqual(len(initial_matches), 0)

        # Toggle to available: now 1 match
        donor_pool[0]["availability"] = 1
        updated_matches = find_best_donors(donor_pool, "AB+", "Wakad")
        self.assertEqual(len(updated_matches), 1)
        self.assertEqual(updated_matches[0]["donor_id"], 5)

        # Toggle back to unavailable: 0 matches again
        donor_pool[0]["availability"] = 0
        toggled_off_matches = find_best_donors(donor_pool, "AB+", "Wakad")
        self.assertEqual(len(toggled_off_matches), 0)


class TestFrontendDonorManagementElements(unittest.TestCase):
    """Test frontend markup contains required management elements and accessible modal"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_home_page_contains_donor_management_section(self):
        """Verify index.html contains donor management section, toolbar, and edit modal"""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Navigation link
        self.assertIn('href="#donor-management"', html)
        self.assertIn('Manage Donors', html)

        # Management container and elements
        self.assertIn('id="donor-management"', html)
        self.assertIn('id="donor-mgmt-filter-input"', html)
        self.assertIn('id="donor-mgmt-avail-filter"', html)
        self.assertIn('id="donor-mgmt-count-badge"', html)
        self.assertIn('id="btn-refresh-donors"', html)
        self.assertIn('id="donor-mgmt-alert"', html)
        self.assertIn('id="donors-mgmt-grid"', html)

        # Ethical disclaimer notice regarding availability
        self.assertIn('Note on Availability:', html)
        self.assertIn('does not represent medical clearance', html)

        # Accessible Edit Modal
        self.assertIn('id="donor-edit-modal"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn('id="donor-edit-form"', html)
        self.assertIn('id="edit-donor-id"', html)
        self.assertIn('id="edit-name"', html)
        self.assertIn('id="edit-age"', html)
        self.assertIn('id="edit-blood-group"', html)
        self.assertIn('id="edit-phone"', html)
        self.assertIn('id="edit-location"', html)
        self.assertIn('id="edit-availability"', html)
        self.assertIn('id="btn-save-donor"', html)
        self.assertIn('id="btn-close-modal"', html)


if __name__ == "__main__":
    unittest.main()
