"""Run a short automated showcase against the seeded local platform."""

from auth.service import AuthError


def run_full_demo(container):
    try:
        user = container.auth.register("demo@example.com", "Demo Student", "demo-password")
    except AuthError as error:
        if "already exists" not in str(error):
            raise
        user = container.database.fetchone("SELECT id, email, name, role FROM users WHERE email = ?",
                                            ("demo@example.com",))
    exams = container.mock_tests.list_exams()
    attempt = container.mock_tests.start(user["id"], exams[0]["id"])
    result = container.mock_tests.submit(user["id"], attempt["id"], {})
    scenario = container.interviews.list_scenarios()[0]
    interview = container.interviews.practice(
        user["id"], scenario["id"], "Situation: team task. Task: meet goal. Action: collaborated. Result: delivered.", 3)
    print(f"Demo complete: {len(exams)} exams, test score {result['score']}/{result['total']}, "
          f"interview rubric score {interview['score']}%.")
