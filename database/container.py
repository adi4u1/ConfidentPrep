"""Dependency container and first-run sample-data loader."""

import json

from auth.service import AuthService
from config import ADMIN_EMAIL, ADMIN_PASSWORD, BASE_DIR, DATABASE_PATH
from services.admin_service import AdminService
from services.contribution_service import ContributionService
from services.interview_service import InterviewService
from services.mock_test_service import MockTestService

from .adapter import DatabaseAdapter


class PlatformContainer:
    def __init__(self, database_path=DATABASE_PATH, seed=True):
        self.database = DatabaseAdapter(database_path)
        self.auth = AuthService(self.database)
        self.mock_tests = MockTestService(self.database)
        self.interviews = InterviewService(self.database)
        self.contributions = ContributionService(self.database)
        self.admin = AdminService(self.database)
        if seed:
            self.seed_sample_data()
            if ADMIN_PASSWORD:
                self.auth.ensure_admin(ADMIN_EMAIL, "Platform Admin", ADMIN_PASSWORD)

    def seed_sample_data(self):
        if self.database.fetchone("SELECT id FROM exams LIMIT 1"):
            return
        data_path = BASE_DIR / "data" / "sample_exam_dataset.json"
        with data_path.open(encoding="utf-8") as file:
            dataset = json.load(file)
        with self.database.transaction() as connection:
            for exam in dataset["exams"]:
                cursor = connection.execute(
                    """INSERT INTO exams(name, category, description, duration_minutes, negative_marking)
                       VALUES (?, ?, ?, ?, ?)""",
                    (exam["name"], exam["category"], exam.get("description", ""),
                     exam["duration_minutes"], exam.get("negative_marking", 0)),
                )
                exam_id = cursor.lastrowid
                for question in exam["questions"]:
                    connection.execute(
                        """INSERT INTO questions
                           (exam_id, topic, difficulty, prompt, options_json, answer, explanation)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (exam_id, question["topic"], question["difficulty"], question["prompt"],
                         json.dumps(question["options"]), question["answer"],
                         question.get("explanation", "")),
                    )
            for scenario in dataset["interview_scenarios"]:
                connection.execute(
                    """INSERT INTO interview_scenarios(category, topic, prompt, rubric_json)
                       VALUES (?, ?, ?, ?)""",
                    (scenario["category"], scenario["topic"], scenario["prompt"],
                     json.dumps(scenario["rubric"])),
                )

    def close(self):
        self.database.close()
