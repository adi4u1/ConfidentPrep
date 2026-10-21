"""Administrative user, exam, moderation, and KPI operations."""

import json


class AdminService:
    def __init__(self, database):
        self.database = database

    def list_users(self):
        return self.database.fetchall(
            "SELECT id, email, name, role, created_at FROM users ORDER BY id"
        )

    def set_user_role(self, user_id, role):
        if role not in ("student", "admin"):
            raise ValueError("Role must be student or admin.")
        cursor = self.database.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if cursor.rowcount == 0:
            raise ValueError("User not found.")
        return self.database.fetchone(
            "SELECT id, email, name, role FROM users WHERE id = ?", (user_id,)
        )

    def delete_user(self, user_id):
        cursor = self.database.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            raise ValueError("User not found.")

    def create_exam(self, name, category, description, duration_minutes, negative_marking=0):
        if not name.strip() or not category.strip():
            raise ValueError("Exam name and category are required.")
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or duration_minutes <= 0:
            raise ValueError("Duration must be a positive integer.")
        if isinstance(negative_marking, bool) or not isinstance(negative_marking, (int, float)) or negative_marking < 0:
            raise ValueError("Negative marking must be a non-negative number.")
        cursor = self.database.execute(
            """INSERT INTO exams(name, category, description, duration_minutes, negative_marking)
               VALUES (?, ?, ?, ?, ?)""",
            (name.strip(), category.strip(), description.strip(), duration_minutes, negative_marking),
        )
        return self.database.fetchone("SELECT * FROM exams WHERE id = ?", (cursor.lastrowid,))

    def update_exam(self, exam_id, name, category, description, duration_minutes,
                    negative_marking=0):
        if not name.strip() or not category.strip():
            raise ValueError("Exam name and category are required.")
        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or duration_minutes <= 0:
            raise ValueError("Duration must be a positive integer.")
        if isinstance(negative_marking, bool) or not isinstance(negative_marking, (int, float)) or negative_marking < 0:
            raise ValueError("Negative marking must be a non-negative number.")
        cursor = self.database.execute(
            """UPDATE exams SET name = ?, category = ?, description = ?,
               duration_minutes = ?, negative_marking = ? WHERE id = ?""",
            (name.strip(), category.strip(), description.strip(), duration_minutes,
             negative_marking, exam_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Exam not found.")
        return self.database.fetchone("SELECT * FROM exams WHERE id = ?", (exam_id,))

    def delete_exam(self, exam_id):
        with self.database.transaction() as connection:
            exam = connection.execute("SELECT id FROM exams WHERE id = ?", (exam_id,)).fetchone()
            if not exam:
                raise ValueError("Exam not found.")
            attempts = connection.execute(
                "SELECT 1 FROM test_attempts WHERE exam_id = ? LIMIT 1", (exam_id,)
            ).fetchone()
            if attempts:
                raise ValueError("An exam with test history cannot be deleted.")
            connection.execute("DELETE FROM exams WHERE id = ?", (exam_id,))

    def add_question(self, exam_id, topic, difficulty, prompt, options, answer, explanation=""):
        if difficulty not in ("easy", "medium", "hard"):
            raise ValueError("Difficulty must be easy, medium, or hard.")
        if not topic.strip() or not prompt.strip() or not isinstance(options, list) or len(options) < 2:
            raise ValueError("Question needs a topic, prompt, and at least two options.")
        if answer not in options:
            raise ValueError("Correct answer must match one of the options.")
        cursor = self.database.execute(
            """INSERT INTO questions(exam_id, topic, difficulty, prompt, options_json, answer, explanation)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (exam_id, topic.strip(), difficulty, prompt.strip(),
             json.dumps(options), answer, explanation.strip()),
        )
        return self.database.fetchone("SELECT id, exam_id FROM questions WHERE id = ?", (cursor.lastrowid,))

    def moderate(self, contribution_id, status):
        if status not in ("approved", "rejected"):
            raise ValueError("Moderation status must be approved or rejected.")
        cursor = self.database.execute(
            "UPDATE contributions SET status = ? WHERE id = ?", (status, contribution_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Contribution not found.")
        return self.database.fetchone("SELECT * FROM contributions WHERE id = ?", (contribution_id,))

    def pending_contributions(self):
        return self.database.fetchall(
            """SELECT c.id, u.name AS author, c.title, c.topic, c.question, c.solution, c.created_at
               FROM contributions c JOIN users u ON u.id = c.user_id
               WHERE c.status = 'pending' ORDER BY c.created_at"""
        )

    def dashboard(self):
        return {
            "users": self.database.fetchone("SELECT COUNT(*) AS total FROM users")["total"],
            "students": self.database.fetchone(
                "SELECT COUNT(*) AS total FROM users WHERE role = 'student'")["total"],
            "exams": self.database.fetchone("SELECT COUNT(*) AS total FROM exams")["total"],
            "questions": self.database.fetchone("SELECT COUNT(*) AS total FROM questions")["total"],
            "test_attempts": self.database.fetchone(
                "SELECT COUNT(*) AS total FROM test_attempts")["total"],
            "completed_tests": self.database.fetchone(
                "SELECT COUNT(*) AS total FROM test_attempts WHERE status = 'completed'")["total"],
            "interview_practices": self.database.fetchone(
                "SELECT COUNT(*) AS total FROM interview_attempts")["total"],
            "pending_contributions": self.database.fetchone(
                "SELECT COUNT(*) AS total FROM contributions WHERE status = 'pending'")["total"],
        }
