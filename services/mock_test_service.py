"""Timed exam attempts, scoring, and performance analytics."""

import json
from datetime import datetime, timedelta, timezone


class TestServiceError(ValueError):
    pass


class MockTestService:
    def __init__(self, database):
        self.database = database

    def list_exams(self):
        return self.database.fetchall(
            """SELECT e.id, e.name, e.category, e.description, e.duration_minutes,
                      e.negative_marking, COUNT(q.id) AS question_count
               FROM exams e LEFT JOIN questions q ON q.exam_id = e.id
               GROUP BY e.id ORDER BY e.name"""
        )

    def start(self, user_id, exam_id):
        exam = self.database.fetchone("SELECT * FROM exams WHERE id = ?", (exam_id,))
        if not exam:
            raise TestServiceError("Exam not found.")
        questions = self.database.fetchall(
            "SELECT id FROM questions WHERE exam_id = ? ORDER BY id", (exam_id,)
        )
        if not questions:
            raise TestServiceError("This exam has no questions.")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """INSERT INTO test_attempts(user_id, exam_id, total_questions, status)
                   VALUES (?, ?, ?, 'in_progress')""",
                (user_id, exam_id, len(questions)),
            )
            attempt_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO attempt_answers(attempt_id, question_id) VALUES (?, ?)",
                [(attempt_id, question["id"]) for question in questions],
            )
        return self.get_attempt(user_id, attempt_id)

    def get_attempt(self, user_id, attempt_id):
        attempt = self.database.fetchone(
            """SELECT a.*, e.name AS exam_name, e.duration_minutes
               FROM test_attempts a JOIN exams e ON e.id = a.exam_id
               WHERE a.id = ? AND a.user_id = ?""",
            (attempt_id, user_id),
        )
        if not attempt:
            raise TestServiceError("Test attempt not found.")
        started = datetime.fromisoformat(attempt["started_at"].replace(" ", "T") + "+00:00")
        deadline = started + timedelta(minutes=attempt["duration_minutes"])
        attempt["deadline"] = deadline.isoformat()
        if attempt["status"] == "in_progress" and datetime.now(timezone.utc) > deadline:
            self.database.execute(
                "UPDATE test_attempts SET status = 'expired', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (attempt_id,),
            )
            attempt["status"] = "expired"
        attempt["questions"] = self.database.fetchall(
            """SELECT q.id, q.topic, q.difficulty, q.prompt, q.options_json
               FROM attempt_answers aa JOIN questions q ON q.id = aa.question_id
               WHERE aa.attempt_id = ? ORDER BY q.id""",
            (attempt_id,),
        )
        for question in attempt["questions"]:
            question["options"] = json.loads(question.pop("options_json"))
        return attempt

    def submit(self, user_id, attempt_id, answers):
        if not isinstance(answers, dict):
            raise TestServiceError("Answers must be an object keyed by question ID.")
        attempt = self.get_attempt(user_id, attempt_id)
        if attempt["status"] != "in_progress":
            raise TestServiceError(f"This attempt is {attempt['status']} and cannot be submitted.")
        question_rows = self.database.fetchall(
            """SELECT q.id, q.answer, q.topic, q.difficulty
               FROM attempt_answers aa JOIN questions q ON q.id = aa.question_id
               WHERE aa.attempt_id = ?""",
            (attempt_id,),
        )
        by_id = {str(row["id"]): row for row in question_rows}
        if any(str(key) not in by_id for key in answers):
            raise TestServiceError("Answers include a question that is not in this attempt.")
        for key, selected in answers.items():
            options = self.database.fetchone(
                "SELECT options_json FROM questions WHERE id = ?", (int(key),)
            )
            if selected is not None and selected not in json.loads(options["options_json"]):
                raise TestServiceError(f"Answer for question {key} is not one of its options.")
        correct = 0
        wrong = 0
        details = []
        with self.database.transaction() as connection:
            for question_id, question in by_id.items():
                selected = answers.get(question_id, answers.get(int(question_id)))
                is_correct = selected == question["answer"] if selected is not None else None
                if is_correct is True:
                    correct += 1
                elif selected is not None:
                    wrong += 1
                connection.execute(
                    """UPDATE attempt_answers SET selected_answer = ?, is_correct = ?
                       WHERE attempt_id = ? AND question_id = ?""",
                    (selected, None if is_correct is None else int(is_correct), attempt_id,
                     question["id"]),
                )
                details.append({
                    "question_id": question["id"], "topic": question["topic"],
                    "difficulty": question["difficulty"], "selected_answer": selected,
                    "correct_answer": question["answer"], "is_correct": is_correct,
                })
            exam = connection.execute(
                "SELECT negative_marking FROM exams WHERE id = ?", (attempt["exam_id"],)
            ).fetchone()
            score = max(0.0, correct - wrong * exam["negative_marking"])
            connection.execute(
                """UPDATE test_attempts SET score = ?, status = 'completed',
                   completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (score, attempt_id),
            )
        total = len(question_rows)
        return {
            "attempt_id": attempt_id, "score": score, "correct": correct, "wrong": wrong,
            "unanswered": total - correct - wrong, "total": total,
            "percentage": round(score / total * 100, 2) if total else 0,
            "analytics": self._analytics(details), "answers": details,
        }

    @staticmethod
    def _analytics(details):
        result = {}
        for field in ("topic", "difficulty"):
            groups = {}
            for item in details:
                group = groups.setdefault(item[field], {"correct": 0, "answered": 0, "total": 0})
                group["total"] += 1
                if item["selected_answer"] is not None:
                    group["answered"] += 1
                if item["is_correct"]:
                    group["correct"] += 1
            result[field] = groups
        return result

    def history(self, user_id):
        return self.database.fetchall(
            """SELECT a.id, e.name AS exam, a.started_at, a.completed_at, a.score,
                      a.total_questions, a.status
               FROM test_attempts a JOIN exams e ON e.id = a.exam_id
               WHERE a.user_id = ? ORDER BY a.id DESC""", (user_id,)
        )
