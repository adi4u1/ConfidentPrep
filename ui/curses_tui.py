"""Arrow-key navigable curses interface for core student and admin workflows."""


def run_curses_tui(container):
    import curses

    def write(screen, row, text, attr=0):
        height, width = screen.getmaxyx()
        if row < height:
            screen.addnstr(row, 2, str(text), max(0, width - 4), attr)

    def prompt(screen, label, secret=False):
        screen.clear()
        lines = str(label).splitlines()
        for row, line in enumerate(lines):
            write(screen, row, line, curses.A_BOLD if row == 0 else 0)
        height, width = screen.getmaxyx()
        input_row = min(len(lines) + 1, height - 1)
        write(screen, input_row, "> ")
        screen.move(input_row, 4)
        curses.curs_set(1)
        if secret:
            curses.noecho()
        else:
            curses.echo()
        try:
            value = screen.getstr(input_row, 4, max(1, min(240, width - 5))).decode("utf-8")
        finally:
            curses.noecho()
            curses.curs_set(0)
        return value

    def pause(screen, message):
        screen.clear()
        for row, line in enumerate(str(message).splitlines()):
            write(screen, row, line, curses.A_BOLD if row == 0 else 0)
        write(screen, min(len(str(message).splitlines()) + 1, screen.getmaxyx()[0] - 1),
              "Press any key to continue.")
        screen.getch()

    def choose(screen, title, options):
        selected = 0
        while True:
            screen.clear()
            write(screen, 0, title, curses.A_BOLD)
            write(screen, 1, "Use arrow keys or j/k, then press Enter.")
            for index, option in enumerate(options):
                write(screen, index + 3, option, curses.A_REVERSE if index == selected else 0)
            key = screen.getch()
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(options)
            elif key in (10, 13, curses.KEY_ENTER):
                return selected

    def exam_catalog(screen):
        exams = container.mock_tests.list_exams()
        lines = [f"{e['id']}. {e['name']} [{e['category']}] — "
                 f"{e['question_count']} questions, {e['duration_minutes']} min" for e in exams]
        pause(screen, "\n".join(["Exam catalog", *lines]))

    def take_test(screen, user):
        raw_id = prompt(screen, "Enter exam ID (blank to cancel):")
        if not raw_id:
            return
        attempt = container.mock_tests.start(user["id"], int(raw_id))
        answers = {}
        for question in attempt["questions"]:
            options = question["options"]
            lines = [question["prompt"]] + [
                f"{index}. {option}" for index, option in enumerate(options, 1)
            ] + ["Enter option number, or blank to skip."]
            selected = prompt(screen, "\n".join(lines))
            if selected.isdecimal() and 1 <= int(selected) <= len(options):
                answers[question["id"]] = options[int(selected) - 1]
        result = container.mock_tests.submit(user["id"], attempt["id"], answers)
        pause(screen, f"Score: {result['score']}/{result['total']} "
                      f"({result['percentage']}%). Topic analytics: {result['analytics']['topic']}")

    def practice_interview(screen, user):
        scenarios = container.interviews.list_scenarios()
        lines = [f"{item['id']}. {item['category']} — {item['topic']}: {item['prompt']}"
                 for item in scenarios]
        raw_id = prompt(screen, "\n".join(["Interview scenarios", *lines, "Scenario ID:"]))
        if not raw_id:
            return
        scenario_id = int(raw_id)
        answer = prompt(screen, "Type your answer:")
        confidence = int(prompt(screen, "Confidence from 1 to 5:"))
        result = container.interviews.practice(user["id"], scenario_id, answer, confidence)
        pause(screen, f"Rubric score: {result['score']}%. {result['feedback']}")

    def create_contribution(screen, user):
        title = prompt(screen, "Contribution title:")
        topic = prompt(screen, "Topic:")
        question = prompt(screen, "Question:")
        solution = prompt(screen, "Solution:")
        container.contributions.submit(user["id"], title, topic, question, solution)
        pause(screen, "Submission sent to the moderation queue.")

    def moderate(screen):
        pending = container.admin.pending_contributions()
        if not pending:
            pause(screen, "There are no pending contributions.")
            return
        rows = [f"{item['id']}. {item['title']} — {item['topic']} (by {item['author']})"
                for item in pending]
        raw_id = prompt(screen, "\n".join(["Pending contributions", *rows, "Submission ID:"]))
        if not raw_id:
            return
        decision = choose(screen, "Moderation decision", ["Approve", "Reject", "Cancel"])
        if decision != 2:
            container.admin.moderate(
                int(raw_id), "approved" if decision == 0 else "rejected"
            )
            pause(screen, "Moderation decision saved.")

    def app(screen):
        curses.curs_set(0)
        while True:
            action = choose(screen, "PyPrep Pro", ["Log in", "Register", "Quit"])
            if action == 2:
                return
            try:
                if action == 1:
                    email = prompt(screen, "Email:")
                    name = prompt(screen, "Name:")
                    password = prompt(screen, "Password (8+ characters):", secret=True)
                    container.auth.register(email, name, password)
                    pause(screen, "Account created. You can now log in.")
                    continue
                email = prompt(screen, "Email:")
                password = prompt(screen, "Password:", secret=True)
                login = container.auth.login(email, password)
                token, user = login["token"], login["user"]
                while True:
                    if user["role"] == "admin":
                        options = ["Usage dashboard", "Moderate contributions",
                                   "Exam catalog", "Log out"]
                    else:
                        options = ["Take a mock test", "Practice an interview",
                                   "Submit a question", "Browse approved contributions",
                                   "Confidence history", "Exam catalog", "Log out"]
                    selected = choose(screen, f"Welcome, {user['name']}", options)
                    try:
                        if user["role"] == "admin":
                            if selected == 0:
                                pause(screen, str(container.admin.dashboard()))
                            elif selected == 1:
                                moderate(screen)
                            elif selected == 2:
                                exam_catalog(screen)
                            else:
                                container.auth.logout(token)
                                break
                        elif selected == 0:
                            take_test(screen, user)
                        elif selected == 1:
                            practice_interview(screen, user)
                        elif selected == 2:
                            create_contribution(screen, user)
                        elif selected == 3:
                            contributions = container.contributions.list_public()
                            lines = [f"{item['title']} — {item['topic']} "
                                     f"(rating {item['average_rating'] or 'unrated'})"
                                     for item in contributions]
                            pause(screen, "\n".join(["Approved contributions", *lines]))
                        elif selected == 4:
                            history = container.interviews.confidence_history(user["id"])
                            pause(screen, str(history))
                        elif selected == 5:
                            exam_catalog(screen)
                        else:
                            container.auth.logout(token)
                            break
                    except (ValueError, TypeError) as error:
                        pause(screen, f"Error: {error}")
            except (ValueError, TypeError) as error:
                pause(screen, f"Error: {error}")

    curses.wrapper(app)
