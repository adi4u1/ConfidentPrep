"""Small JSON WSGI router, with no mandatory web-framework dependency."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import parse_qs

from auth.service import AuthError

logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    method: str
    path: str
    query: dict
    body: dict
    token: str
    user: dict | None = None


class FlaskCompatRouter:
    """WSGI API router that can run with Python's built-in WSGI server."""

    def __init__(self, container):
        self.container = container

    @staticmethod
    def _response(start_response, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        phrase = HTTPStatus(status).phrase
        start_response(
            f"{status} {phrase}",
            [("Content-Type", "application/json; charset=utf-8"),
             ("Content-Length", str(len(body))), ("Cache-Control", "no-store")],
        )
        return [body]

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(environ.get("QUERY_STRING", "")).items()}
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length > 1_000_000:
                return self._response(start_response, 413, {"error": "Request body exceeds 1 MB."})
            raw = environ["wsgi.input"].read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("JSON request body must be an object.")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return self._response(start_response, 400, {"error": f"Invalid JSON request: {error}"})
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        context = RequestContext(method, path, query, body, token)
        try:
            status, payload = self._dispatch(context)
            return self._response(start_response, status, payload)
        except AuthError as error:
            status = 403 if str(error) == "Insufficient permissions." else 401
            return self._response(start_response, status, {"error": str(error)})
        except (ValueError, TypeError, KeyError) as error:
            return self._response(start_response, 400, {"error": str(error)})
        except sqlite3.IntegrityError as error:
            return self._response(start_response, 400, {"error": str(error)})
        except Exception:
            logger.exception("Unhandled API error for %s %s", method, path)
            return self._response(start_response, 500, {"error": "Internal server error."})

    def _user(self, context, role=None):
        context.user = self.container.auth.authenticate(context.token, role)
        return context.user

    def _dispatch(self, context):
        method, path, body = context.method, context.path, context.body
        if method == "GET" and path == "/":
            return 200, {"name": "PyPrep Pro API", "version": "1.0", "health": "/api/health"}
        if method == "GET" and path == "/api/health":
            return 200, {"status": "ok"}
        if method == "POST" and path == "/api/register":
            return 201, {"user": self.container.auth.register(
                body.get("email", ""), body.get("name", ""), body.get("password", ""))}
        if method == "POST" and path == "/api/login":
            return 200, self.container.auth.login(body.get("email", ""), body.get("password", ""))
        if method == "POST" and path == "/api/logout":
            self._user(context)
            self.container.auth.logout(context.token)
            return 200, {"message": "Logged out."}
        if method == "GET" and path == "/api/exams":
            return 200, {"exams": self.container.mock_tests.list_exams()}
        if method == "POST" and path == "/api/tests":
            user = self._user(context)
            return 201, self.container.mock_tests.start(user["id"], body.get("exam_id"))
        if method == "GET" and path == "/api/tests/history":
            user = self._user(context)
            return 200, {"attempts": self.container.mock_tests.history(user["id"])}
        if method == "POST" and path.startswith("/api/tests/") and path.endswith("/submit"):
            user = self._user(context)
            attempt_id = self._numeric_suffix(path[:-7].rstrip("/"), "/api/tests/")
            return 200, self.container.mock_tests.submit(
                user["id"], attempt_id, body.get("answers", {}))
        if method == "GET" and path.startswith("/api/tests/"):
            user = self._user(context)
            attempt_id = self._numeric_suffix(path, "/api/tests/")
            return 200, self.container.mock_tests.get_attempt(user["id"], attempt_id)
        if method == "GET" and path == "/api/interviews":
            self._user(context)
            return 200, {"scenarios": self.container.interviews.list_scenarios(
                context.query.get("category"))}
        if method == "POST" and path == "/api/interviews/practice":
            user = self._user(context)
            return 201, self.container.interviews.practice(
                user["id"], body.get("scenario_id"), body.get("answer", ""),
                body.get("confidence"))
        if method == "GET" and path == "/api/interviews/confidence":
            user = self._user(context)
            return 200, {"history": self.container.interviews.confidence_history(user["id"])}
        if method == "GET" and path == "/api/contributions":
            self._user(context)
            return 200, {"contributions": self.container.contributions.list_public()}
        if method == "POST" and path == "/api/contributions":
            user = self._user(context)
            return 201, self.container.contributions.submit(
                user["id"], body.get("title", ""), body.get("topic", ""),
                body.get("question", ""), body.get("solution", ""))
        if method == "POST" and path.startswith("/api/contributions/") and path.endswith("/reviews"):
            user = self._user(context)
            contribution_id = self._numeric_suffix(path[:-8].rstrip("/"), "/api/contributions/")
            return 200, self.container.contributions.review(
                user["id"], contribution_id, body.get("rating"), body.get("review", ""))
        if method == "GET" and path == "/api/admin/dashboard":
            self._user(context, "admin")
            return 200, self.container.admin.dashboard()
        if method == "GET" and path == "/api/admin/users":
            self._user(context, "admin")
            return 200, {"users": self.container.admin.list_users()}
        if method == "PATCH" and path.startswith("/api/admin/users/"):
            actor = self._user(context, "admin")
            user_id = self._numeric_suffix(path, "/api/admin/users/")
            if user_id == actor["id"]:
                raise ValueError("You cannot change your own role.")
            return 200, self.container.admin.set_user_role(user_id, body.get("role"))
        if method == "DELETE" and path.startswith("/api/admin/users/"):
            actor = self._user(context, "admin")
            user_id = self._numeric_suffix(path, "/api/admin/users/")
            if user_id == actor["id"]:
                raise ValueError("You cannot delete your own account.")
            self.container.admin.delete_user(user_id)
            return 200, {"message": "User deleted."}
        if method == "GET" and path == "/api/admin/contributions":
            self._user(context, "admin")
            return 200, {"contributions": self.container.admin.pending_contributions()}
        if method == "POST" and path.startswith("/api/admin/contributions/") and path.endswith("/moderate"):
            self._user(context, "admin")
            contribution_id = self._numeric_suffix(path[:-9].rstrip("/"), "/api/admin/contributions/")
            return 200, self.container.admin.moderate(contribution_id, body.get("status"))
        if method == "POST" and path == "/api/admin/exams":
            self._user(context, "admin")
            return 201, self.container.admin.create_exam(
                body.get("name", ""), body.get("category", ""), body.get("description", ""),
                body.get("duration_minutes"), body.get("negative_marking", 0))
        if method == "PUT" and path.startswith("/api/admin/exams/"):
            self._user(context, "admin")
            exam_id = self._numeric_suffix(path, "/api/admin/exams/")
            return 200, self.container.admin.update_exam(
                exam_id, body.get("name", ""), body.get("category", ""),
                body.get("description", ""), body.get("duration_minutes"),
                body.get("negative_marking", 0))
        if method == "DELETE" and path.startswith("/api/admin/exams/"):
            self._user(context, "admin")
            exam_id = self._numeric_suffix(path, "/api/admin/exams/")
            self.container.admin.delete_exam(exam_id)
            return 200, {"message": "Exam deleted."}
        if method == "POST" and path == "/api/admin/questions":
            self._user(context, "admin")
            return 201, self.container.admin.add_question(
                body.get("exam_id"), body.get("topic", ""), body.get("difficulty", ""),
                body.get("prompt", ""), body.get("options"), body.get("answer", ""),
                body.get("explanation", ""))
        return 404, {"error": "Endpoint not found."}

    @staticmethod
    def _numeric_suffix(path, prefix):
        suffix = path[len(prefix):]
        if not suffix.isdecimal():
            raise ValueError("Resource ID must be a positive integer.")
        return int(suffix)
