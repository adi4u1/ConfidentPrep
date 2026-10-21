"""Student question submissions and peer reviews."""


class ContributionService:
    def __init__(self, database):
        self.database = database

    def submit(self, user_id, title, topic, question, solution):
        values = [value.strip() if isinstance(value, str) else "" for value in
                  (title, topic, question, solution)]
        if any(not value for value in values):
            raise ValueError("Title, topic, question, and solution are required.")
        cursor = self.database.execute(
            """INSERT INTO contributions(user_id, title, topic, question, solution)
               VALUES (?, ?, ?, ?, ?)""", (user_id, *values)
        )
        return self.get(cursor.lastrowid)

    def get(self, contribution_id):
        contribution = self.database.fetchone(
            """SELECT c.id, c.user_id, u.name AS author, c.title, c.topic, c.question,
                      c.solution, c.status, c.created_at,
                      ROUND(AVG(r.rating), 2) AS average_rating, COUNT(r.rating) AS review_count
               FROM contributions c JOIN users u ON u.id = c.user_id
               LEFT JOIN contribution_reviews r ON r.contribution_id = c.id
               WHERE c.id = ? GROUP BY c.id""", (contribution_id,)
        )
        if not contribution:
            raise ValueError("Contribution not found.")
        return contribution

    def list_public(self):
        return self.database.fetchall(
            """SELECT c.id, c.user_id, u.name AS author, c.title, c.topic, c.question,
                      c.solution, c.status, c.created_at,
                      ROUND(AVG(r.rating), 2) AS average_rating, COUNT(r.rating) AS review_count
               FROM contributions c JOIN users u ON u.id = c.user_id
               LEFT JOIN contribution_reviews r ON r.contribution_id = c.id
               WHERE c.status = 'approved' GROUP BY c.id ORDER BY c.created_at DESC"""
        )

    def review(self, reviewer_id, contribution_id, rating, review=""):
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise ValueError("Rating must be an integer from 1 to 5.")
        contribution = self.get(contribution_id)
        if contribution["user_id"] == reviewer_id:
            raise ValueError("You cannot review your own contribution.")
        if contribution["status"] != "approved":
            raise ValueError("Only approved contributions can be reviewed.")
        self.database.execute(
            """INSERT INTO contribution_reviews(contribution_id, user_id, rating, review)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(contribution_id, user_id) DO UPDATE SET
               rating = excluded.rating, review = excluded.review, created_at = CURRENT_TIMESTAMP""",
            (contribution_id, reviewer_id, rating, review.strip()),
        )
        return self.get(contribution_id)
