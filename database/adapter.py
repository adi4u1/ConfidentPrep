"""SQLite persistence adapter and application schema."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'admin')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    negative_marking REAL NOT NULL DEFAULT 0 CHECK (negative_marking >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL,
    answer TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS test_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_id INTEGER NOT NULL REFERENCES exams(id),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    score REAL,
    total_questions INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'expired'))
);
CREATE TABLE IF NOT EXISTS attempt_answers (
    attempt_id INTEGER NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    selected_answer TEXT,
    is_correct INTEGER,
    PRIMARY KEY (attempt_id, question_id)
);
CREATE TABLE IF NOT EXISTS interview_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK (category IN ('HR', 'Technical')),
    topic TEXT NOT NULL,
    prompt TEXT NOT NULL,
    rubric_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interview_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scenario_id INTEGER NOT NULL REFERENCES interview_scenarios(id),
    answer TEXT NOT NULL,
    score REAL NOT NULL,
    feedback TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 5),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    solution TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contribution_reviews (
    contribution_id INTEGER NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contribution_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions(exam_id);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON test_attempts(user_id, started_at);
CREATE INDEX IF NOT EXISTS idx_contributions_status ON contributions(status, created_at);
"""


class DatabaseAdapter:
    """Thread-safe SQLite adapter with explicit transaction support."""

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None, timeout=30
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        with self._lock:
            self.connection.executescript(SCHEMA)

    def execute(self, sql, parameters=()):
        with self._lock:
            return self.connection.execute(sql, parameters)

    def fetchone(self, sql, parameters=()):
        with self._lock:
            row = self.connection.execute(sql, parameters).fetchone()
            return dict(row) if row is not None else None

    def fetchall(self, sql, parameters=()):
        with self._lock:
            return [dict(row) for row in self.connection.execute(sql, parameters).fetchall()]

    @contextmanager
    def transaction(self):
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except Exception:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def close(self):
        with self._lock:
            self.connection.close()
