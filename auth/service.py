"""Password hashing, bearer sessions, and role checks."""

import hashlib
import hmac
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone

from config import PASSWORD_ITERATIONS, SESSION_TTL_HOURS


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _hash_password(password, salt=None):
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
        return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password, encoded):
        try:
            algorithm, iterations, salt_hex, expected = encoded.split("$")
            if algorithm != "pbkdf2_sha256":
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
            ).hex()
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def register(self, email, name, password):
        email = email.strip().lower()
        name = name.strip()
        if not email or "@" not in email or not name:
            raise AuthError("A valid email and name are required.")
        if len(password) < 8:
            raise AuthError("Password must contain at least 8 characters.")
        try:
            cursor = self.database.execute(
                "INSERT INTO users(email, name, password_hash, role) VALUES (?, ?, ?, 'student')",
                (email, name, self._hash_password(password)),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise AuthError("An account with this email already exists.") from error
            raise
        return self.database.fetchone(
            "SELECT id, email, name, role, created_at FROM users WHERE id = ?", (cursor.lastrowid,)
        )

    def ensure_admin(self, email, name, password):
        email = email.strip().lower()
        if len(password) < 8:
            raise AuthError("Password must contain at least 8 characters.")
        user = self.database.fetchone("SELECT id FROM users WHERE email = ?", (email,))
        if user:
            self.database.execute(
                "UPDATE users SET role = 'admin', password_hash = ? WHERE id = ?",
                (self._hash_password(password), user["id"]),
            )
            return
        self.database.execute(
            "INSERT INTO users(email, name, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (email, name, self._hash_password(password)),
        )

    def login(self, email, password):
        user = self.database.fetchone("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        if not user or not self._verify_password(password, user["password_hash"]):
            raise AuthError("Invalid email or password.")
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        self.database.execute(
            "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (self._token_hash(token), user["id"], expires.isoformat()),
        )
        return {
            "token": token,
            "expires_at": expires.isoformat(),
            "user": {key: user[key] for key in ("id", "email", "name", "role")},
        }

    def authenticate(self, token, required_role=None):
        if not token:
            raise AuthError("Bearer token is required.")
        session = self.database.fetchone(
            """SELECT u.id, u.email, u.name, u.role, s.expires_at
               FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
            (self._token_hash(token),),
        )
        if not session:
            raise AuthError("Invalid or expired session.")
        if datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
            self.database.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))
            raise AuthError("Invalid or expired session.")
        if required_role and session["role"] != required_role:
            raise AuthError("Insufficient permissions.")
        return {key: session[key] for key in ("id", "email", "name", "role")}

    def logout(self, token):
        self.database.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))
