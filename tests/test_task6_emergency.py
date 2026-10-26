"""
Unit and Integration Tests for BloodLink Task 6:
Emergency Request Status Updates, Filtering, and Existing Functionality.
Uses Flask test_client and unittest.mock to ensure the active database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime

from app import app
from matching import find_best_donors, is_compatible, bubble_sort


class TestEmergencyStatusUpdateMocked(unittest.TestCase):
    """Tests for PUT/PATCH /emergency/<request_id>/status and /emergency/<request_id>"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_update_status_to_fulfilled_success(self, mock_get_db):
        """Test successfully updating an active request to FULFILLED"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock existing request
        mock_cursor.fetchone.return_value = {
            "request_id": 1,
            "request_status": "ACTIVE"
        }

        response = self.client.put(
            "/emergency/1/status",
            data=json.dumps({"status": "FULFILLED"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "FULFILLED")
        self.assertEqual(data["previous_status"], "ACTIVE")
        self.assertEqual(data["request_id"], 1)

        # Verify SQL execution and commit
        mock_cursor.execute.assert_any_call(
            "UPDATE emergency_requests SET request_status = %s WHERE request_id = %s",
            ("FULFILLED", 1)
        )
        mock_db.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_update_status_to_cancelled_success(self, mock_get_db):
        """Test successfully updating an active request to CANCELLED via PATCH /emergency/<id>"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 2,
            "request_status": "ACTIVE"
        }

        response = self.client.patch(
            "/emergency/2",
            data=json.dumps({"status": "CANCELLED"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "CANCELLED")
        self.assertEqual(data["previous_status"], "ACTIVE")

        mock_cursor.execute.assert_any_call(
            "UPDATE emergency_requests SET request_status = %s WHERE request_id = %s",
            ("CANCELLED", 2)
        )
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_update_status_case_insensitive_and_alternate_key(self, mock_get_db):
        """Test status normalization (lowercase 'fulfilled') and 'request_status' JSON key"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 3,
            "request_status": "ACTIVE"
        }

        response = self.client.put(
            "/emergency/3/status",
            data=json.dumps({"request_status": "fulfilled"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "FULFILLED")

    @patch("app.get_db_connection")
    def test_update_status_to_active(self, mock_get_db):
        """Test re-activating a request with 'ACTIVE' status"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 4,
            "request_status": "CANCELLED"
        }

        response = self.client.put(
            "/emergency/4/status",
            data=json.dumps({"status": "ACTIVE"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ACTIVE")
        self.assertEqual(data["previous_status"], "CANCELLED")

    def test_update_invalid_status_value(self):
        """Test rejecting invalid status values (PENDING, RESOLVED, etc.)"""
        invalid_statuses = ["PENDING", "COMPLETED", "RESOLVED", "DELETED", "IN_PROGRESS", "123", ""]
        for st in invalid_statuses:
            response = self.client.put(
                "/emergency/1/status",
                data=json.dumps({"status": st}),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 400, f"Status '{st}' should return 400")
            data = response.get_json()
            self.assertIn("error", data)

    def test_update_missing_status_field(self):
        """Test rejecting request with missing status field"""
        response = self.client.put(
            "/emergency/1/status",
            data=json.dumps({"other_field": "val"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_update_empty_or_non_json_body(self):
        """Test rejecting invalid JSON body"""
        response = self.client.put(
            "/emergency/1/status",
            data="not-a-json",
            content_type="text/plain"
        )
        self.assertEqual(response.status_code, 400)

    def test_update_invalid_request_id(self):
        """Test rejecting invalid request_id <= 0"""
        response = self.client.put(
            "/emergency/0/status",
            data=json.dumps({"status": "FULFILLED"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("app.get_db_connection")
    def test_update_nonexistent_request_id(self, mock_get_db):
        """Test 404 error when emergency request ID does not exist"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # fetchone returns None -> request not found
        mock_cursor.fetchone.return_value = None

        response = self.client.put(
            "/emergency/99999/status",
            data=json.dumps({"status": "FULFILLED"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertIn("not found", data["error"].lower())

    @patch("app.get_db_connection")
    def test_update_db_error_triggers_rollback(self, mock_get_db):
        """Test 500 error and rollback when database fails during update"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"request_id": 1, "request_status": "ACTIVE"}
        mock_cursor.execute.side_effect = [None, Exception("Simulated DB connection failure")]

        response = self.client.put(
            "/emergency/1/status",
            data=json.dumps({"status": "FULFILLED"}),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 500)
        mock_db.rollback.assert_called_once()


class TestEmergencyGetFilteringMocked(unittest.TestCase):
    """Tests for GET /emergency and GET /emergency/<id> with mocked DB"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"

    @patch("app.get_db_connection")
    def test_get_emergency_default_active_only(self, mock_get_db):
        """Test that GET /emergency defaults to ACTIVE requests only"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {"request_id": 1, "request_status": "ACTIVE", "blood_group_required": "O+"}
        ]

        response = self.client.get("/emergency")
        self.assertEqual(response.status_code, 200)

        # Verify SQL query specifically filtered for ACTIVE
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM emergency_requests WHERE request_status='ACTIVE' ORDER BY request_id DESC"
        )

    @patch("app.get_db_connection")
    def test_get_emergency_history_filter(self, mock_get_db):
        """Test GET /emergency?status=history returns fulfilled and cancelled requests"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {"request_id": 2, "request_status": "FULFILLED"},
            {"request_id": 3, "request_status": "CANCELLED"}
        ]

        response = self.client.get("/emergency?status=history")
        self.assertEqual(response.status_code, 200)

        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM emergency_requests WHERE request_status IN ('FULFILLED', 'CANCELLED') ORDER BY request_id DESC"
        )

    @patch("app.get_db_connection")
    def test_get_emergency_all_filter(self, mock_get_db):
        """Test GET /emergency?status=all returns all requests"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"request_id": 1, "request_status": "ACTIVE"}
        ]

        response = self.client.get("/emergency?status=all")
        self.assertEqual(response.status_code, 200)

        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM emergency_requests ORDER BY request_id DESC"
        )

    def test_get_emergency_invalid_filter(self):
        """Test GET /emergency with invalid status filter returns 400"""
        response = self.client.get("/emergency?status=INVALID_FILTER")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    @patch("app.get_db_connection")
    def test_get_single_emergency_success(self, mock_get_db):
        """Test GET /emergency/<id> retrieves single record"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 1,
            "request_status": "ACTIVE",
            "blood_group_required": "O+",
            "units_required": 2
        }

        response = self.client.get("/emergency/1")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["request_id"], 1)

    @patch("app.get_db_connection")
    def test_get_single_emergency_not_found(self, mock_get_db):
        """Test GET /emergency/<id> returns 404 for nonexistent ID"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None

        response = self.client.get("/emergency/99999")
        self.assertEqual(response.status_code, 404)


class TestExistingFunctionalityPreserved(unittest.TestCase):
    """Tests to verify donor search, donor registration, emergency creation, and algorithms remain intact"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999
            sess["user_name"] = "Admin Tester"
            sess["user_role"] = "ADMIN"

    def test_matching_algorithm_compatibility(self):
        """Verify blood compatibility rules in matching.py"""
        # Universal donor O- can donate to all
        for recipient in ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]:
            self.assertTrue(is_compatible("O-", recipient), f"O- should be compatible with {recipient}")

        # Universal recipient AB+ can receive from all
        for donor in ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]:
            self.assertTrue(is_compatible(donor, "AB+"), f"{donor} should be compatible with AB+")

        # Incompatible pairings: A+ cannot donate to B+ or O+
        self.assertFalse(is_compatible("A+", "B+"))
        self.assertFalse(is_compatible("A+", "O+"))
        self.assertFalse(is_compatible("B+", "A+"))
        self.assertFalse(is_compatible("AB+", "O+"))

    def test_scoring_and_bubble_sort(self):
        """Verify scoring and sorting logic"""
        donors = [
            {"donor_id": 1, "blood_group": "A+", "location": "Mumbai", "availability": 1},
            {"donor_id": 2, "blood_group": "A+", "location": "Pune", "availability": 1},
            {"donor_id": 3, "blood_group": "O+", "location": "Pune", "availability": 1},
            {"donor_id": 4, "blood_group": "B+", "location": "Pune", "availability": 1},
        ]
        # For recipient A+ in Pune:
        # donor 2: Exact (60) + City (20) = 80
        # donor 3: Compatible (40) + City (20) = 60
        # donor 1: Exact (60) + Diff City (0) = 60
        # donor 4: Incompatible -> excluded
        matched = find_best_donors(donors, "A+", "Pune")
        self.assertEqual(len(matched), 3)
        self.assertEqual(matched[0]["donor_id"], 2)
        self.assertEqual(matched[0]["matching_score"], 80)

    @patch("app.get_db_connection")
    def test_find_donors_endpoint(self, mock_get_db):
        """Test /find-donors route"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {"donor_id": 1, "name": "Test Donor", "blood_group": "O+", "location": "Pune", "availability": 1}
        ]

        response = self.client.get("/find-donors", query_string={"blood_group": "O+", "location": "Pune"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["recipient_blood_group"], "O+")
        self.assertGreaterEqual(data["total_matches"], 1)

    def test_find_donors_missing_blood_group(self):
        """Test /find-donors requires blood_group"""
        response = self.client.get("/find-donors")
        self.assertEqual(response.status_code, 400)

    def test_donor_registration_validation(self):
        """Test donor registration validations without touching DB"""
        # Invalid age < 18
        res = self.client.post("/donors", json={"name": "Bob", "age": 15, "blood_group": "A+", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

        # Invalid blood group
        res = self.client.post("/donors", json={"name": "Bob", "age": 25, "blood_group": "XYZ", "phone": "9876543210", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

        # Missing phone
        res = self.client.post("/donors", json={"name": "Bob", "age": 25, "blood_group": "A+", "phone": "", "location": "Pune"})
        self.assertEqual(res.status_code, 400)

    def test_emergency_creation_validation(self):
        """Test emergency request validations without touching DB"""
        # Invalid units > 20
        res = self.client.post("/emergency", json={"blood_group_required": "O+", "units_required": 50, "emergency_level": "CRITICAL"})
        self.assertEqual(res.status_code, 400)

        # Invalid priority level
        res = self.client.post("/emergency", json={"blood_group_required": "O+", "units_required": 2, "emergency_level": "UNKNOWN"})
        self.assertEqual(res.status_code, 400)

        # Invalid blood group
        res = self.client.post("/emergency", json={"blood_group_required": "INVALID", "units_required": 2, "emergency_level": "HIGH"})
        self.assertEqual(res.status_code, 400)

    def test_home_page_renders_elements(self):
        """Test home page loads with required Task 6 elements"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Verify active board elements exist
        self.assertIn('id="emergency-requests"', html)
        self.assertIn('id="emergency-cards-container"', html)
        self.assertIn('id="emergency-update-alert"', html)

        # Verify archive section elements exist
        self.assertIn('id="emergency-archive-container"', html)
        self.assertIn('id="archive-cards-container"', html)
        self.assertIn('id="btn-refresh-archive"', html)


if __name__ == "__main__":
    unittest.main()
