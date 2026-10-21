"""Interactive student and administrator terminal menus."""

from getpass import getpass

from auth.service import AuthError
from .formatters import print_table


class TerminalCLI:
    def __init__(self, container):
        self.container = container

    def run(self):
        while True:
            print("\nPyPrep Pro | 1 Register  2 Login  0 Exit")
            choice = input("> ").strip()
            try:
                if choice == "0":
                    return
                if choice == "1":
                    user = self.container.auth.register(
                        input("Email: "), input("Name: "), getpass("Password: "))
                    print(f"Account created for {user['name']}. Please log in.")
                elif choice == "2":
                    result = self.container.auth.login(
                        input("Email: "), getpass("Password: "))
                    self._menu(result["token"], result["user"])
                else:
                    print("Choose one of the listed options.")
            except (ValueError, AuthError) as error:
                print(f"Error: {error}")

    def _menu(self, token, user):
        while True:
            if user["role"] == "admin":
                print("\n1 Exams  2 Admin dashboard  3 Moderate submissions  4 Logout")
            else:
                print("\n1 Exams  2 Interview practice  3 Contribute  4 Browse contributions  5 Logout")
            choice = input("> ").strip()
            try:
                if user["role"] == "admin":
                    if choice == "1":
                        self._exams(user)
                    elif choice == "2":
                        print(self.container.admin.dashboard())
                    elif choice == "3":
                        self._moderate()
                    elif choice == "4":
                        self.container.auth.logout(token)
                        return
                else:
                    if choice == "1":
                        self._exams(user)
                    elif choice == "2":
                        self._interview(user)
                    elif choice == "3":
                        self.container.contributions.submit(
                            user["id"], input("Title: "), input("Topic: "),
                            input("Question: "), input("Solution: "))
                        print("Submission received for moderation.")
                    elif choice == "4":
                        contributions = self.container.contributions.list_public()
                        print_table(["ID", "Title", "Topic", "Rating"], [
                            (item["id"], item["title"], item["topic"], item["average_rating"] or "-")
                            for item in contributions])
                    elif choice == "5":
                        self.container.auth.logout(token)
                        return
                    else:
                        print("Choose one of the listed options.")
            except (ValueError, AuthError) as error:
                print(f"Error: {error}")

    def _exams(self, user):
        exams = self.container.mock_tests.list_exams()
        print_table(["ID", "Exam", "Category", "Questions", "Minutes"],
                    [(e["id"], e["name"], e["category"], e["question_count"], e["duration_minutes"])
                     for e in exams])
        raw_exam_id = input("Exam ID (0 to cancel): ").strip()
        if raw_exam_id == "0":
            return
        try:
            attempt = self.container.mock_tests.start(user["id"], int(raw_exam_id))
        except ValueError as error:
            print(f"Error: {error}")
            return
        answers = {}
        for question in attempt["questions"]:
            print(f"\n{question['prompt']}")
            for index, option in enumerate(question["options"], 1):
                print(f"  {index}. {option}")
            selection = input("Answer number (blank to skip): ").strip()
            if selection.isdecimal() and 1 <= int(selection) <= len(question["options"]):
                answers[question["id"]] = question["options"][int(selection) - 1]
        result = self.container.mock_tests.submit(user["id"], attempt["id"], answers)
        print(f"Score: {result['score']}/{result['total']} ({result['percentage']}%)")
        print(f"Topic analytics: {result['analytics']['topic']}")

    def _interview(self, user):
        scenarios = self.container.interviews.list_scenarios()
        print_table(["ID", "Type", "Topic", "Prompt"],
                    [(s["id"], s["category"], s["topic"], s["prompt"]) for s in scenarios])
        scenario_id = int(input("Scenario ID: "))
        answer = input("Your answer: ")
        confidence = int(input("Confidence (1-5): "))
        result = self.container.interviews.practice(user["id"], scenario_id, answer, confidence)
        print(f"Rubric score: {result['score']}% — {result['feedback']}")

    def _moderate(self):
        pending = self.container.admin.pending_contributions()
        print_table(["ID", "Author", "Title", "Topic"],
                    [(item["id"], item["author"], item["title"], item["topic"]) for item in pending])
        if pending:
            contribution_id = int(input("Submission ID: "))
            decision = input("Approve or reject [a/r]: ").strip().lower()
            self.container.admin.moderate(
                contribution_id, "approved" if decision == "a" else "rejected")
            print("Moderation decision saved.")
