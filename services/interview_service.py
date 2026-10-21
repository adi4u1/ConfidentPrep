"""Interview scenario practice and confidence tracking."""

import json


class InterviewService:
    def __init__(self, database):
        self.database = database

    def list_scenarios(self, category=None):
        if category:
            category = category.title()
            if category not in ("Hr", "Technical"):
                raise ValueError("Category must be HR or Technical.")
            return self.database.fetchall(
                "SELECT id, category, topic, prompt FROM interview_scenarios WHERE category = ? ORDER BY id",
                ("HR" if category == "Hr" else category,),
            )
        return self.database.fetchall(
            "SELECT id, category, topic, prompt FROM interview_scenarios ORDER BY id"
        )

    def practice(self, user_id, scenario_id, answer, confidence):
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("An interview answer is required.")
        if isinstance(confidence, bool) or not isinstance(confidence, int) or not 1 <= confidence <= 5:
            raise ValueError("Confidence must be an integer from 1 to 5.")
        scenario = self.database.fetchone(
            "SELECT * FROM interview_scenarios WHERE id = ?", (scenario_id,)
        )
        if not scenario:
            raise ValueError("Interview scenario not found.")
        rubric = json.loads(scenario["rubric_json"])
        normalized = answer.casefold()
        matched = [criterion for criterion in rubric if criterion.casefold() in normalized]
        score = round(len(matched) / len(rubric) * 100, 2) if rubric else 0
        missing = [criterion for criterion in rubric if criterion not in matched]
        feedback = (
            f"Addressed {len(matched)} of {len(rubric)} rubric points. "
            + (f"Consider adding: {', '.join(missing)}." if missing else "Good coverage; add specific evidence where possible.")
        )
        cursor = self.database.execute(
            """INSERT INTO interview_attempts(user_id, scenario_id, answer, score, feedback, confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, scenario_id, answer.strip(), score, feedback, confidence),
        )
        return self.database.fetchone(
            "SELECT * FROM interview_attempts WHERE id = ?", (cursor.lastrowid,)
        )

    def confidence_history(self, user_id):
        return self.database.fetchall(
            """SELECT ia.created_at, s.category, s.topic, ia.confidence, ia.score
               FROM interview_attempts ia JOIN interview_scenarios s ON s.id = ia.scenario_id
               WHERE ia.user_id = ? ORDER BY ia.id""", (user_id,)
        )
