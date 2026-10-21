"""Unit and WSGI integration tests for PyPrep Pro."""

import io
import json
import unittest

from api import FlaskCompatRouter
from auth.service import AuthError
from database import PlatformContainer


class PlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.container = PlatformContainer(":memory:")
        self.user = self.container.auth.register(
            "student@example.com", "Test Student", "password-123"
        )
        self.token = self.container.auth.login("student@example.com", "password-123")["token"]
        self.router = FlaskCompatRouter(self.container)

    def tearDown(self):
        self.container.close()

    def request(self, method, path, body=None, token=None):
        encoded = json.dumps(body or {}).encode()
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(encoded)), "wsgi.input": io.BytesIO(encoded),
        }
        if token:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split()[0])
            captured["headers"] = headers

        response = b"".join(self.router(environ, start_response))
        return captured["status"], json.loads(response)

    def test_registration_rejects_duplicate_and_password_is_not_stored_plaintext(self):
        stored = self.container.database.fetchone(
            "SELECT password_hash FROM users WHERE id = ?", (self.user["id"],)
        )["password_hash"]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(stored, "password-123")
        with self.assertRaises(AuthError):
            self.container.auth.register("student@example.com", "Another", "password-123")

    def test_test_attempt_scores_negative_marking_and_topic_analytics(self):
        exam = next(exam for exam in self.container.mock_tests.list_exams()
                    if exam["name"] == "TCS NQT")
        attempt = self.container.mock_tests.start(self.user["id"], exam["id"])
        questions = attempt["questions"]
        first = questions[0]
        first_answer = self.container.database.fetchone(
            "SELECT answer FROM questions WHERE id = ?", (first["id"],)
        )["answer"]
        second = questions[1]
        second_answer = self.container.database.fetchone(
            "SELECT answer FROM questions WHERE id = ?", (second["id"],)
        )["answer"]
        wrong_answer = next(option for option in second["options"] if option != second_answer)
        with self.assertRaises(ValueError):
            self.container.mock_tests.submit(
                self.user["id"], attempt["id"], {first["id"]: "not a valid option"}
            )
        result = self.container.mock_tests.submit(
            self.user["id"], attempt["id"], {first["id"]: first_answer, second["id"]: wrong_answer}
        )
        self.assertEqual(result["total"], exam["question_count"])
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["wrong"], 1)
        self.assertEqual(result["unanswered"], exam["question_count"] - 2)
        self.assertEqual(result["score"], 0.75)
        self.assertIn("topic", result["analytics"])
        with self.assertRaises(ValueError):
            self.container.mock_tests.submit(self.user["id"], attempt["id"], {})

    def test_contribution_moderation_and_peer_review(self):
        contribution = self.container.contributions.submit(
            self.user["id"], "A practice question", "Algebra", "What is 2+2?", "4"
        )
        with self.assertRaises(ValueError):
            self.container.contributions.review(self.user["id"], contribution["id"], 5)
        self.container.admin.moderate(contribution["id"], "approved")
        reviewer = self.container.auth.register(
            "reviewer@example.com", "Reviewer", "password-456"
        )
        reviewed = self.container.contributions.review(
            reviewer["id"], contribution["id"], 5, "Clear explanation."
        )
        self.assertEqual(reviewed["average_rating"], 5)
        self.assertEqual(len(self.container.contributions.list_public()), 1)

    def test_admin_routes_enforce_roles_and_dashboard(self):
        status, payload = self.request("GET", "/api/admin/dashboard", token=self.token)
        self.assertEqual(status, 403)
        self.container.auth.ensure_admin("admin@example.com", "Admin", "admin-pass-123")
        admin_token = self.container.auth.login("admin@example.com", "admin-pass-123")["token"]
        status, payload = self.request("GET", "/api/admin/dashboard", token=admin_token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(payload["exams"], 3)

    def test_api_login_exams_and_history_routes(self):
        status, login = self.request("POST", "/api/login", {
            "email": "student@example.com", "password": "password-123",
        })
        self.assertEqual(status, 200)
        status, exams = self.request("GET", "/api/exams")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(exams["exams"]), 3)
        status, _ = self.request("GET", "/api/tests/history", token=login["token"])
        self.assertEqual(status, 200)
        status, attempt = self.request(
            "POST", "/api/tests", {"exam_id": exams["exams"][0]["id"]}, login["token"]
        )
        self.assertEqual(status, 201)
        status, result = self.request(
            "POST", f"/api/tests/{attempt['id']}/submit", {"answers": {}}, login["token"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["unanswered"], attempt["total_questions"])

    def test_timer_expiration_and_attempt_isolation(self):
        attempt = self.container.mock_tests.start(self.user["id"], 1)
        other = self.container.auth.register("other@example.com", "Other", "password-789")
        with self.assertRaises(ValueError):
            self.container.mock_tests.get_attempt(other["id"], attempt["id"])
        self.container.database.execute(
            "UPDATE test_attempts SET started_at = '2000-01-01 00:00:00' WHERE id = ?",
            (attempt["id"],),
        )
        expired = self.container.mock_tests.get_attempt(self.user["id"], attempt["id"])
        self.assertEqual(expired["status"], "expired")

    def test_admin_exam_management_and_user_role(self):
        self.container.auth.ensure_admin("admin@example.com", "Admin", "admin-pass-123")
        self.container.auth.login("admin@example.com", "admin-pass-123")
        exam = self.container.admin.create_exam("Custom", "Practice", "", 10)
        changed = self.container.admin.update_exam(
            exam["id"], "Custom Updated", "Practice", "Description", 15, 0.5
        )
        self.assertEqual(changed["duration_minutes"], 15)
        self.container.admin.set_user_role(self.user["id"], "admin")
        self.assertEqual(
            self.container.database.fetchone("SELECT role FROM users WHERE id = ?",
                                             (self.user["id"],))["role"], "admin"
        )
        self.container.admin.delete_exam(exam["id"])


if __name__ == "__main__":
    unittest.main()
