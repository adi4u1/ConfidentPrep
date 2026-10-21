"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("PYPREP_DATABASE", BASE_DIR / "pyprep.db"))
SESSION_TTL_HOURS = int(os.getenv("PYPREP_SESSION_TTL_HOURS", "24"))
PASSWORD_ITERATIONS = int(os.getenv("PYPREP_PASSWORD_ITERATIONS", "310000"))
API_HOST = os.getenv("PYPREP_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("PYPREP_API_PORT", "8000"))
ADMIN_EMAIL = os.getenv("PYPREP_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("PYPREP_ADMIN_PASSWORD")
