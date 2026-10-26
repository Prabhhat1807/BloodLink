"""
Unit and Integration Tests for BloodLink Task 9:
Recipient Registration & Management — Form Validation, Directory, Search & Filtering, Profile Editing, and Integration Compatibility.
Uses Flask test_client and unittest.mock to ensure the active database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json

from app import app


class TestRecipientRegistration(unittest.TestCase):
    """Tests for POST /recipients (Recipient Registration)"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"

    @patch("app.get_db_connection")
    def test_register_recipient_full_success(self, mock_get_db):
        """Test successfully registering a recipient with all supported fields"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock hospital existence check
        mock_cursor.fetchone.return_value = {"hospital_id": 1}
        mock_cursor.lastrowid = 101

        payload = {
            "name": "Siddharth Rao",
            "age": 28,
            "gender": "Male",
            "blood_group": "AB+",
            "phone": "9876543210",
            "location": "Baner, Pune",
            "hospital_id": 1,
            "units_required": 2,
            "emergency_level": "CRITICAL"
        }

        response = self.client.post(
            "/recipients",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["recipient_id"], 101)
        self.assertEqual(data["message"], "Recipient registered successfully")
        self.assertEqual(data["recipient"]["name"], "Siddharth Rao")
        self.assertEqual(data["recipient"]["blood_group"], "AB+")
        self.assertEqual(data["recipient"]["units_required"], 2)
        self.assertEqual(data["recipient"]["emergency_level"], "CRITICAL")

        mock_db.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_register_recipient_minimal_required_fields(self, mock_get_db):
        """Test registering a recipient with only the required fields, verifying defaults"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 102

        payload = {
            "name": "Kavita Deshmukh",
            "age": 45,
            "blood_group": "O-",
            "phone": "9123456780",
            "location": "Shivaji Nagar"
        }

        response = self.client.post(
            "/recipients",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["recipient_id"], 102)
        self.assertEqual(data["recipient"]["units_required"], 1)
        self.assertEqual(data["recipient"]["emergency_level"], "NORMAL")
        self.assertIsNone(data["recipient"]["gender"])
        self.assertIsNone(data["recipient"]["hospital_id"])

        mock_db.commit.assert_called_once()

    def test_register_recipient_non_dict_payload(self):
        """Test registration rejection when body is not a JSON object"""
        response = self.client.post(
            "/recipients",
            data="not a json string",
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_register_recipient_missing_name(self):
        """Test registration rejection with missing or too short name"""
        payload = {
            "name": "A",
            "age": 30,
            "blood_group": "A+",
            "phone": "9876543210",
            "location": "Pune"
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.get_json()["error"].lower())

    def test_register_recipient_missing_age(self):
        """Test registration rejection when age is missing"""
        payload = {
            "name": "Rohan Joshi",
            "blood_group": "A+",
            "phone": "9876543210",
            "location": "Pune"
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("age", response.get_json()["error"].lower())

    def test_register_recipient_invalid_age_out_of_range(self):
        """Test age boundary rejection (< 1 or > 120)"""
        for invalid_age in [0, -5, 121, 200]:
            payload = {
                "name": "Rohan Joshi",
                "age": invalid_age,
                "blood_group": "A+",
                "phone": "9876543210",
                "location": "Pune"
            }
            response = self.client.post("/recipients", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("age", response.get_json()["error"].lower())

    def test_register_recipient_non_numeric_age(self):
        """Test age rejection when string is not an integer"""
        payload = {
            "name": "Rohan Joshi",
            "age": "thirty",
            "blood_group": "A+",
            "phone": "9876543210",
            "location": "Pune"
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("whole number", response.get_json()["error"].lower())

    def test_register_recipient_invalid_blood_group(self):
        """Test blood group validation against accepted medical blood groups"""
        for bad_bg in ["C+", "O", "POSITIVE", "", "XYZ"]:
            payload = {
                "name": "Rohan Joshi",
                "age": 32,
                "blood_group": bad_bg,
                "phone": "9876543210",
                "location": "Pune"
            }
            response = self.client.post("/recipients", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("blood group", response.get_json()["error"].lower())

    def test_register_recipient_invalid_phone(self):
        """Test phone number validation (between 7 and 15 digits)"""
        for bad_phone in ["12345", "phone123", "", "1" * 16]:
            payload = {
                "name": "Rohan Joshi",
                "age": 32,
                "blood_group": "B+",
                "phone": bad_phone,
                "location": "Pune"
            }
            response = self.client.post("/recipients", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("phone", response.get_json()["error"].lower())

    def test_register_recipient_missing_location(self):
        """Test location validation"""
        payload = {
            "name": "Rohan Joshi",
            "age": 32,
            "blood_group": "B+",
            "phone": "9876543210",
            "location": " "
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("location", response.get_json()["error"].lower())

    def test_register_recipient_invalid_units(self):
        """Test units required validation (1 to 20)"""
        for bad_units in [0, 21, -1, "five"]:
            payload = {
                "name": "Rohan Joshi",
                "age": 32,
                "blood_group": "B+",
                "phone": "9876543210",
                "location": "Pune",
                "units_required": bad_units
            }
            response = self.client.post("/recipients", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("units_required", response.get_json()["error"].lower())

    def test_register_recipient_invalid_emergency_level(self):
        """Test emergency urgency level validation"""
        payload = {
            "name": "Rohan Joshi",
            "age": 32,
            "blood_group": "B+",
            "phone": "9876543210",
            "location": "Pune",
            "emergency_level": "EXTREME_SUPER"
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("emergency_level", response.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_register_recipient_nonexistent_hospital(self, mock_get_db):
        """Test rejecting an invalid hospital ID that does not exist in database"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # Hospital not found

        payload = {
            "name": "Rohan Joshi",
            "age": 32,
            "blood_group": "B+",
            "phone": "9876543210",
            "location": "Pune",
            "hospital_id": 999
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("hospital does not exist", response.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_register_recipient_database_error_rollback(self, mock_get_db):
        """Test server error and transaction rollback when database insertion fails"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("MySQL Disk Full")

        payload = {
            "name": "Rohan Joshi",
            "age": 32,
            "blood_group": "B+",
            "phone": "9876543210",
            "location": "Pune"
        }
        response = self.client.post("/recipients", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())
        mock_db.rollback.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()


class TestRecipientDirectoryAndSearch(unittest.TestCase):
    """Tests for GET /recipients and search/filter query parameters"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_get_all_recipients_success(self, mock_get_db):
        """Test GET /recipients returning a list of all recipients"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        sample_recipients = [
            {
                "recipient_id": 1,
                "name": "Arjun Mehta",
                "age": 30,
                "gender": "Male",
                "blood_group": "O+",
                "phone": "9000000001",
                "location": "Pune",
                "hospital_id": 1,
                "units_required": 2,
                "emergency_level": "HIGH",
                "hospital_name": "City Hospital",
                "hospital_city": "Pune"
            },
            {
                "recipient_id": 2,
                "name": "Anjali Verma",
                "age": 25,
                "gender": "Female",
                "blood_group": "B+",
                "phone": "9000000002",
                "location": "Pimpri",
                "hospital_id": 2,
                "units_required": 1,
                "emergency_level": "NORMAL",
                "hospital_name": "Apex Trauma Center",
                "hospital_city": "Pimpri"
            }
        ]
        mock_cursor.fetchall.return_value = sample_recipients

        response = self.client.get("/recipients")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["name"], "Arjun Mehta")

    @patch("app.get_db_connection")
    def test_search_recipients_by_name(self, mock_get_db):
        """Test searching recipients by name query param"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/recipients?search=Arjun")
        self.assertEqual(response.status_code, 200)

        # Verify SQL executed with LIKE filter
        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("r.name LIKE %s", sql_call[0])
        self.assertIn("%Arjun%", sql_call[1])

    @patch("app.get_db_connection")
    def test_filter_recipients_by_blood_group(self, mock_get_db):
        """Test filtering recipients by blood group"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/recipients?blood_group=O+")
        self.assertEqual(response.status_code, 200)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("r.blood_group = %s", sql_call[0])
        self.assertIn("O+", sql_call[1])

    @patch("app.get_db_connection")
    def test_filter_recipients_by_location(self, mock_get_db):
        """Test filtering recipients by location/city"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/recipients?location=Pune")
        self.assertEqual(response.status_code, 200)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("r.location LIKE %s", sql_call[0])
        self.assertIn("%Pune%", sql_call[1])

    @patch("app.get_db_connection")
    def test_filter_recipients_combined(self, mock_get_db):
        """Test combined filters: name, blood group, location, emergency_level"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/recipients?name=Arjun&blood_group=O+&location=Pune&emergency_level=HIGH")
        self.assertEqual(response.status_code, 200)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("r.name LIKE %s", sql_call[0])
        self.assertIn("r.blood_group = %s", sql_call[0])
        self.assertIn("r.location LIKE %s", sql_call[0])
        self.assertIn("r.emergency_level = %s", sql_call[0])

    @patch("app.get_db_connection")
    def test_get_recipients_db_error(self, mock_get_db):
        """Test error handling when database query fails"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB Connection Timeout")

        response = self.client.get("/recipients")
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())

    @patch("app.get_db_connection")
    def test_get_single_recipient_success(self, mock_get_db):
        """Test retrieving a single recipient profile by ID"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 1,
            "name": "Arjun Mehta",
            "age": 30,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune",
            "hospital_id": 1,
            "units_required": 2,
            "emergency_level": "HIGH",
            "hospital_name": "City Hospital",
            "hospital_city": "Pune"
        }

        response = self.client.get("/recipients/1")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["recipient_id"], 1)
        self.assertEqual(data["name"], "Arjun Mehta")

    @patch("app.get_db_connection")
    def test_get_single_recipient_not_found(self, mock_get_db):
        """Test 404 response for nonexistent recipient ID"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        response = self.client.get("/recipients/999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"].lower())

    def test_get_single_recipient_invalid_id(self):
        """Test 400 response for non-positive recipient ID"""
        response = self.client.get("/recipients/0")
        self.assertEqual(response.status_code, 400)
        self.assertIn("positive integer", response.get_json()["error"].lower())


class TestRecipientEdit(unittest.TestCase):
    """Tests for PUT /recipients/<recipient_id> and PATCH /recipients/<recipient_id>"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_update_recipient_put_success(self, mock_get_db):
        """Test successfully updating an existing recipient via full PUT"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock existing recipient lookup
        mock_cursor.fetchone.side_effect = [
            {
                "recipient_id": 1,
                "name": "Arjun Mehta",
                "age": 30,
                "gender": "Male",
                "blood_group": "O+",
                "phone": "9000000001",
                "location": "Pune",
                "hospital_id": 1,
                "units_required": 2,
                "emergency_level": "HIGH"
            },
            {"hospital_id": 2}  # Hospital check
        ]

        payload = {
            "name": "Arjun R. Mehta",
            "age": 31,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9000000099",
            "location": "Kothrud, Pune",
            "hospital_id": 2,
            "units_required": 3,
            "emergency_level": "CRITICAL"
        }

        response = self.client.put(
            "/recipients/1",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["recipient_id"], 1)
        self.assertEqual(data["recipient"]["name"], "Arjun R. Mehta")
        self.assertEqual(data["recipient"]["age"], 31)
        self.assertEqual(data["recipient"]["phone"], "9000000099")
        self.assertEqual(data["recipient"]["location"], "Kothrud, Pune")
        self.assertEqual(data["recipient"]["units_required"], 3)
        self.assertEqual(data["recipient"]["emergency_level"], "CRITICAL")

        mock_db.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_update_recipient_patch_partial_success(self, mock_get_db):
        """Test partial update via PATCH keeping unspecified existing fields"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 2,
            "name": "Anjali Verma",
            "age": 25,
            "gender": "Female",
            "blood_group": "B+",
            "phone": "9000000002",
            "location": "Pimpri",
            "hospital_id": 2,
            "units_required": 1,
            "emergency_level": "NORMAL"
        }

        # Only update location and emergency level
        payload = {
            "location": "Chinchwad, Pune",
            "emergency_level": "HIGH"
        }

        response = self.client.patch(
            "/recipients/2",
            data=json.dumps(payload),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["recipient"]["name"], "Anjali Verma")  # preserved
        self.assertEqual(data["recipient"]["blood_group"], "B+")      # preserved
        self.assertEqual(data["recipient"]["location"], "Chinchwad, Pune")  # updated
        self.assertEqual(data["recipient"]["emergency_level"], "HIGH")     # updated

        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_update_recipient_not_found(self, mock_get_db):
        """Test 404 response when attempting to update nonexistent recipient"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        response = self.client.put(
            "/recipients/999",
            json={"name": "Unknown Person", "age": 30, "blood_group": "O+", "phone": "9876543210", "location": "Pune"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.get_json()["error"].lower())

    def test_update_recipient_invalid_id(self):
        """Test 400 response for invalid ID <= 0"""
        response = self.client.put("/recipients/0", json={"name": "Test"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("positive integer", response.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_update_recipient_invalid_blood_group(self, mock_get_db):
        """Test update rejection with invalid blood group"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "recipient_id": 1, "name": "Arjun", "age": 30, "blood_group": "O+",
            "phone": "9000000001", "location": "Pune"
        }

        response = self.client.patch("/recipients/1", json={"blood_group": "INVALID"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("blood group", response.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_update_recipient_database_error_rollback(self, mock_get_db):
        """Test database rollback and clean 500 error when update query fails"""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "recipient_id": 1, "name": "Arjun", "age": 30, "blood_group": "O+",
            "phone": "9000000001", "location": "Pune"
        }
        mock_cursor.execute.side_effect = [None, Exception("Deadlock encountered")]

        response = self.client.put(
            "/recipients/1",
            json={"name": "Arjun Updated", "age": 31, "blood_group": "O+", "phone": "9000000001", "location": "Pune"}
        )
        self.assertEqual(response.status_code, 500)
        mock_db.rollback.assert_called_once()


class TestRecipientIntegrationCompatibility(unittest.TestCase):
    """Tests ensuring GET /recipients is backward compatible with existing emergency dropdown consumers"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_emergency_dropdown_format_compatibility(self, mock_get_db):
        """
        Verify that GET /recipients contains all fields used by loadRecipients() in main.js:
        recipient_id, name, blood_group, location, units_required
        """
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {
                "recipient_id": 1,
                "name": "Arjun Mehta",
                "age": 30,
                "gender": "Male",
                "blood_group": "O+",
                "phone": "9000000001",
                "location": "Pune",
                "hospital_id": 1,
                "units_required": 2,
                "emergency_level": "HIGH",
                "hospital_name": "City Hospital",
                "hospital_city": "Pune"
            }
        ]

        response = self.client.get("/recipients")
        self.assertEqual(response.status_code, 200)
        recipients = response.get_json()
        self.assertIsInstance(recipients, list)
        self.assertGreater(len(recipients), 0)

        first = recipients[0]
        # Check all properties required by emergency dropdown
        self.assertIn("recipient_id", first)
        self.assertIn("name", first)
        self.assertIn("blood_group", first)
        self.assertIn("location", first)
        self.assertIn("units_required", first)
        self.assertIn("emergency_level", first)


if __name__ == "__main__":
    unittest.main()
