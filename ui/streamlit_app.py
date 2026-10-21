"""Browser-based graphical interface for PyPrep Pro."""

import sqlite3
from datetime import datetime

import streamlit as st

from database import PlatformContainer


st.set_page_config(
    page_title="PyPrep Pro",
    page_icon=":material/school:",
    layout="wide",
)


@st.cache_resource
def get_container():
    return PlatformContainer()


def show_error(error):
    st.error(str(error))


def login_page(container):
    st.title("PyPrep Pro")
    st.write("Build confidence for your next exam or interview.")
    sign_in, register = st.tabs(["Sign in", "Create account"])

    with sign_in:
        with st.form("sign_in_form"):
            email = st.text_input("Email", key="sign_in_email")
            password = st.text_input("Password", type="password", key="sign_in_password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            try:
                login = container.auth.login(email, password)
                st.session_state["auth_token"] = login["token"]
                st.rerun()
            except ValueError as error:
                show_error(error)

    with register:
        with st.form("register_form"):
            name = st.text_input("Name", key="register_name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input(
                "Password (at least 8 characters)",
                type="password",
                key="register_password",
            )
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            try:
                user = container.auth.register(email, name, password)
                st.success(f"Account created for {user['name']}. Sign in to continue.")
            except ValueError as error:
                show_error(error)


def overview_page(container, user):
    st.title(f"Welcome, {user['name']}")
    history = container.mock_tests.history(user["id"])
    completed = [attempt for attempt in history if attempt["status"] == "completed"]
    exams = container.mock_tests.list_exams()
    average = (
        sum(
            (attempt["score"] or 0) / attempt["total_questions"] * 100
            for attempt in completed if attempt["total_questions"]
        ) / len(completed)
        if completed else 0
    )

    with st.container(horizontal=True):
        st.metric("Available exams", len(exams), border=True)
        st.metric("Completed mock tests", len(completed), border=True)
        st.metric("Average score", f"{average:.1f}%", border=True)

    st.subheader("Recent mock tests")
    if history:
        st.dataframe(history[:10], hide_index=True)
        score_history = [
            {
                "Attempt": f"{attempt['exam']} #{attempt['id']}",
                "Score (%)": round(
                    (attempt["score"] or 0) / attempt["total_questions"] * 100, 1
                ) if attempt["total_questions"] else 0,
            }
            for attempt in reversed(completed[:10])
        ]
        if score_history:
            st.bar_chart(score_history, x="Attempt", y="Score (%)")
    else:
        st.info("Your mock test results will appear here.")

    if user["role"] == "student":
        confidence = container.interviews.confidence_history(user["id"])
        if confidence:
            st.subheader("Interview practice")
            st.line_chart(
                {"Confidence (1–5)": [item["confidence"] for item in confidence]}
            )


def _start_test(container, user, attempt):
    st.session_state["active_attempt_id"] = attempt["id"]
    st.session_state["active_attempt_owner"] = user["id"]
    st.rerun()


@st.fragment(run_every="1s")
def show_test_timer(deadline):
    seconds_remaining = max(
        0,
        int((datetime.fromisoformat(deadline) - datetime.now().astimezone()).total_seconds()),
    )
    minutes, seconds = divmod(seconds_remaining, 60)
    st.metric("Time remaining", f"{minutes:02d}:{seconds:02d}")


def mock_tests_page(container, user):
    st.title("Mock tests")
    active_id = st.session_state.get("active_attempt_id")
    active_owner = st.session_state.get("active_attempt_owner")

    if active_id and active_owner == user["id"]:
        try:
            attempt = container.mock_tests.get_attempt(user["id"], active_id)
        except ValueError as error:
            st.session_state.pop("active_attempt_id", None)
            st.session_state.pop("active_attempt_owner", None)
            show_error(error)
            attempt = None
        if attempt and attempt["status"] == "in_progress":
            st.subheader(attempt["exam_name"])
            deadline = datetime.fromisoformat(attempt["deadline"]).astimezone()
            show_test_timer(attempt["deadline"])
            st.caption(f"Submit your answers before {deadline.strftime('%Y-%m-%d %H:%M:%S %Z')}.")
            with st.form(f"test_attempt_{attempt['id']}"):
                selections = []
                for index, question in enumerate(attempt["questions"], start=1):
                    st.write(f"**Question {index}**")
                    st.write(question["prompt"])
                    answer = st.radio(
                        "Select an answer",
                        options=[None, *question["options"]],
                        format_func=lambda option: "Skip this question" if option is None else option,
                        key=f"answer_{attempt['id']}_{question['id']}",
                        label_visibility="collapsed",
                    )
                    selections.append((question["id"], answer))
                submitted = st.form_submit_button("Submit test", type="primary")
            if submitted:
                answers = {
                    question_id: answer
                    for question_id, answer in selections
                    if answer is not None
                }
                try:
                    result = container.mock_tests.submit(user["id"], attempt["id"], answers)
                    st.session_state["last_test_result"] = result
                    st.session_state.pop("active_attempt_id", None)
                    st.session_state.pop("active_attempt_owner", None)
                    st.rerun()
                except ValueError as error:
                    show_error(error)
            return
        if attempt:
            st.warning(f"This test is {attempt['status']} and can no longer be submitted.")
            st.session_state.pop("active_attempt_id", None)
            st.session_state.pop("active_attempt_owner", None)

    result = st.session_state.get("last_test_result")
    if result:
        st.subheader("Latest result")
        with st.container(border=True):
            st.metric(
                "Score",
                f"{result['score']} / {result['total']}",
                f"{result['percentage']}%",
            )
            st.write(
                f"{result['correct']} correct · {result['wrong']} incorrect · "
                f"{result['unanswered']} unanswered"
            )
            st.dataframe(result["answers"], hide_index=True)
            if st.button("Dismiss result", key="dismiss_test_result"):
                st.session_state.pop("last_test_result", None)
                st.rerun()

    exams = container.mock_tests.list_exams()
    if not exams:
        st.info("No exams are available yet.")
        return

    unfinished = [
        attempt for attempt in container.mock_tests.history(user["id"])
        if attempt["status"] == "in_progress"
    ]
    if unfinished:
        st.subheader("Continue an unfinished test")
        attempt_by_id = {attempt["id"]: attempt for attempt in unfinished}
        attempt_id = st.selectbox(
            "Unfinished test",
            list(attempt_by_id),
            format_func=lambda value: (
                f"{attempt_by_id[value]['exam']} · started "
                f"{attempt_by_id[value]['started_at']}"
            ),
        )
        if st.button("Resume test", type="primary"):
            _start_test(container, user, container.mock_tests.get_attempt(user["id"], attempt_id))

    st.subheader("Exam catalog")
    st.dataframe(exams, hide_index=True)
    selected_exam = st.selectbox(
        "Choose an exam",
        exams,
        format_func=lambda exam: (
            f"{exam['name']} · {exam['category']} · "
            f"{exam['question_count']} questions · {exam['duration_minutes']} minutes"
        ),
    )
    if st.button("Start mock test", type="primary", key="start_mock_test"):
        try:
            attempt = container.mock_tests.start(user["id"], selected_exam["id"])
            _start_test(container, user, attempt)
        except ValueError as error:
            show_error(error)


def interview_page(container, user):
    st.title("Interview practice")
    category = st.selectbox("Interview type", ["All", "HR", "Technical"])
    scenarios = container.interviews.list_scenarios(
        None if category == "All" else category
    )
    if not scenarios:
        st.info("No interview scenarios are available.")
        return

    scenario = st.selectbox(
        "Choose a scenario",
        scenarios,
        format_func=lambda item: f"{item['category']} · {item['topic']}",
    )
    with st.container(border=True):
        st.write(scenario["prompt"])
    with st.form("interview_practice_form"):
        answer = st.text_area("Your answer", height=180)
        confidence = st.slider("How confident do you feel?", 1, 5, 3)
        submitted = st.form_submit_button("Review my answer", type="primary")
    if submitted:
        try:
            result = container.interviews.practice(
                user["id"], scenario["id"], answer, confidence
            )
            st.success(f"Rubric score: {result['score']}%")
            st.write(result["feedback"])
        except ValueError as error:
            show_error(error)

    history = container.interviews.confidence_history(user["id"])
    if history:
        st.subheader("Confidence history")
        st.line_chart(
            {
                "Confidence (1–5)": [item["confidence"] for item in history],
                "Rubric score (%)": [item["score"] for item in history],
            }
        )


def community_page(container, user):
    st.title("Community")
    st.subheader("Share a practice question")
    with st.form("contribution_form"):
        title = st.text_input("Title")
        topic = st.text_input("Topic")
        question = st.text_area("Question")
        solution = st.text_area("Solution")
        submitted = st.form_submit_button("Submit for review", type="primary")
    if submitted:
        try:
            container.contributions.submit(
                user["id"], title, topic, question, solution
            )
            st.success("Your question was sent to the moderation queue.")
        except ValueError as error:
            show_error(error)

    st.subheader("Approved contributions")
    contributions = container.contributions.list_public()
    if not contributions:
        st.info("There are no approved contributions yet.")
        return

    for item in contributions:
        with st.container(border=True):
            st.subheader(item["title"])
            st.caption(
                f"{item['topic']} · by {item['author']} · "
                f"Rating: {item['average_rating'] or 'Not rated'}"
            )
            st.write(item["question"])
            with st.expander("View solution"):
                st.write(item["solution"])
            if item["user_id"] != user["id"]:
                with st.form(f"review_{item['id']}"):
                    rating = st.selectbox(
                        "Your rating",
                        [1, 2, 3, 4, 5],
                        index=4,
                        key=f"rating_{item['id']}",
                    )
                    review = st.text_input(
                        "Review (optional)", key=f"review_text_{item['id']}"
                    )
                    submitted = st.form_submit_button("Save rating")
                if submitted:
                    try:
                        container.contributions.review(
                            user["id"], item["id"], rating, review
                        )
                        st.success("Your rating was saved.")
                        st.rerun()
                    except (ValueError, sqlite3.IntegrityError) as error:
                        show_error(error)


def admin_dashboard_page(container):
    st.title("Admin dashboard")
    dashboard = container.admin.dashboard()
    metrics = [
        ("Users", dashboard["users"]),
        ("Students", dashboard["students"]),
        ("Exams", dashboard["exams"]),
        ("Questions", dashboard["questions"]),
        ("Test attempts", dashboard["test_attempts"]),
        ("Completed tests", dashboard["completed_tests"]),
        ("Interview practices", dashboard["interview_practices"]),
        ("Pending contributions", dashboard["pending_contributions"]),
    ]
    for start in range(0, len(metrics), 4):
        with st.container(horizontal=True):
            for label, value in metrics[start:start + 4]:
                st.metric(label, value, border=True)


def moderation_page(container):
    st.title("Contribution moderation")
    pending = container.admin.pending_contributions()
    if not pending:
        st.success("The moderation queue is clear.")
        return

    for item in pending:
        with st.container(border=True):
            st.subheader(item["title"])
            st.caption(f"{item['topic']} · submitted by {item['author']}")
            st.write(item["question"])
            with st.expander("View suggested solution"):
                st.write(item["solution"])
            approve, reject = st.columns(2)
            if approve.button("Approve", key=f"approve_{item['id']}"):
                try:
                    container.admin.moderate(item["id"], "approved")
                    st.success("Contribution approved.")
                    st.rerun()
                except ValueError as error:
                    show_error(error)
            if reject.button("Reject", key=f"reject_{item['id']}"):
                try:
                    container.admin.moderate(item["id"], "rejected")
                    st.success("Contribution rejected.")
                    st.rerun()
                except ValueError as error:
                    show_error(error)


def exam_management_page(container):
    st.title("Exam management")
    exams = container.mock_tests.list_exams()

    with st.expander("Create an exam"):
        with st.form("create_exam_form"):
            name = st.text_input("Exam name")
            category = st.text_input("Category")
            description = st.text_area("Description")
            duration = st.number_input("Duration (minutes)", min_value=1, value=30)
            negative_marking = st.number_input(
                "Negative marking per incorrect answer", min_value=0.0, value=0.0, step=0.25
            )
            submitted = st.form_submit_button("Create exam", type="primary")
        if submitted:
            try:
                container.admin.create_exam(
                    name, category, description, duration, negative_marking
                )
                st.success("Exam created.")
                st.rerun()
            except (ValueError, sqlite3.IntegrityError) as error:
                show_error(error)

    if not exams:
        st.info("Create an exam before adding questions.")
        return

    st.subheader("Current exams")
    st.dataframe(exams, hide_index=True)
    selected_exam = st.selectbox(
        "Choose an exam to edit",
        exams,
        format_func=lambda exam: f"{exam['name']} · {exam['category']}",
    )
    exam_id = selected_exam["id"]

    with st.expander("Edit exam details"):
        with st.form(f"edit_exam_{exam_id}"):
            name = st.text_input(
                "Exam name", value=selected_exam["name"], key=f"edit_name_{exam_id}"
            )
            category = st.text_input(
                "Category", value=selected_exam["category"], key=f"edit_category_{exam_id}"
            )
            description = st.text_area(
                "Description",
                value=selected_exam["description"],
                key=f"edit_description_{exam_id}",
            )
            duration = st.number_input(
                "Duration (minutes)",
                min_value=1,
                value=selected_exam["duration_minutes"],
                key=f"edit_duration_{exam_id}",
            )
            negative_marking = st.number_input(
                "Negative marking per incorrect answer",
                min_value=0.0,
                value=float(selected_exam["negative_marking"]),
                step=0.25,
                key=f"edit_negative_marking_{exam_id}",
            )
            submitted = st.form_submit_button("Save exam")
        if submitted:
            try:
                container.admin.update_exam(
                    exam_id, name, category, description, duration, negative_marking
                )
                st.success("Exam details updated.")
                st.rerun()
            except (ValueError, sqlite3.IntegrityError) as error:
                show_error(error)

    with st.expander("Add a question"):
        with st.form(f"add_question_{exam_id}"):
            topic = st.text_input("Topic")
            difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"])
            prompt = st.text_area("Question prompt")
            options_text = st.text_area(
                "Answer options (one per line)", placeholder="Option A\nOption B"
            )
            answer = st.text_input("Correct answer (must match an option exactly)")
            explanation = st.text_area("Explanation (optional)")
            submitted = st.form_submit_button("Add question", type="primary")
        if submitted:
            options = [option.strip() for option in options_text.splitlines() if option.strip()]
            try:
                container.admin.add_question(
                    exam_id, topic, difficulty, prompt, options, answer, explanation
                )
                st.success("Question added.")
                st.rerun()
            except ValueError as error:
                show_error(error)

    with st.expander("Delete exam"):
        st.warning("An exam with test history cannot be deleted.")
        confirmed = st.checkbox(
            "I understand this will permanently delete the exam and its questions.",
            key=f"confirm_delete_exam_{exam_id}",
        )
        if st.button("Delete exam", disabled=not confirmed, key=f"delete_exam_{exam_id}"):
            try:
                container.admin.delete_exam(exam_id)
                st.success("Exam deleted.")
                st.rerun()
            except ValueError as error:
                show_error(error)


def user_management_page(container, user):
    st.title("User management")
    users = container.admin.list_users()
    st.dataframe(users, hide_index=True)

    editable_users = [item for item in users if item["id"] != user["id"]]
    if not editable_users:
        st.info("There are no other users to manage.")
        return

    users_by_id = {item["id"]: item for item in editable_users}
    user_id = st.selectbox(
        "Choose a user",
        list(users_by_id),
        format_func=lambda value: (
            f"{users_by_id[value]['name']} · {users_by_id[value]['email']}"
        ),
    )
    selected_user = users_by_id[user_id]
    with st.form(f"change_role_{user_id}"):
        role = st.selectbox(
            "Role",
            ["student", "admin"],
            index=["student", "admin"].index(selected_user["role"]),
        )
        submitted = st.form_submit_button("Save role")
    if submitted:
        try:
            container.admin.set_user_role(user_id, role)
            st.success("User role updated.")
            st.rerun()
        except ValueError as error:
            show_error(error)

    st.warning("Deleting a user permanently removes their account and related history.")
    confirmed = st.checkbox(
        f"Confirm deletion of {selected_user['name']}",
        key=f"confirm_delete_user_{user_id}",
    )
    if st.button("Delete user", disabled=not confirmed, key=f"delete_user_{user_id}"):
        try:
            container.admin.delete_user(user_id)
            st.success("User deleted.")
            st.rerun()
        except ValueError as error:
            show_error(error)


def main():
    container = get_container()
    token = st.session_state.get("auth_token")
    if not token:
        login_page(container)
        return

    try:
        user = container.auth.authenticate(token)
    except ValueError as error:
        st.session_state.pop("auth_token", None)
        show_error(error)
        login_page(container)
        return

    pages = ["Overview", "Mock tests", "Interview practice", "Community"]
    if user["role"] == "admin":
        pages.extend(
            ["Admin dashboard", "Moderation", "Exam management", "User management"]
        )

    with st.sidebar:
        st.title("PyPrep Pro")
        st.caption(f"{user['name']} · {user['role'].title()}")
        page = st.selectbox("Workspace", pages, key="workspace_navigation")
        if st.button("Sign out", icon=":material/logout:"):
            container.auth.logout(token)
            st.session_state.pop("auth_token", None)
            st.session_state.pop("active_attempt_id", None)
            st.session_state.pop("active_attempt_owner", None)
            st.rerun()

    active_attempt_id = st.session_state.get("active_attempt_id")
    if active_attempt_id and st.session_state.get("active_attempt_owner") == user["id"]:
        mock_tests_page(container, user)
        return

    if page == "Overview":
        overview_page(container, user)
    elif page == "Mock tests":
        mock_tests_page(container, user)
    elif page == "Interview practice":
        interview_page(container, user)
    elif page == "Community":
        community_page(container, user)
    elif page == "Admin dashboard" and user["role"] == "admin":
        admin_dashboard_page(container)
    elif page == "Moderation" and user["role"] == "admin":
        moderation_page(container)
    elif page == "Exam management" and user["role"] == "admin":
        exam_management_page(container)
    elif page == "User management" and user["role"] == "admin":
        user_management_page(container, user)


main()
