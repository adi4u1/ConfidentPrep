"""Application entry point for the terminal UI, API, demo, and tests."""

import argparse
import getpass
import logging
import os
import subprocess
import sys
import unittest
from wsgiref.simple_server import make_server

from api import FlaskCompatRouter
from config import ADMIN_EMAIL, API_HOST, API_PORT, BASE_DIR, DATABASE_PATH
from database import PlatformContainer
from ui import TerminalCLI, run_curses_tui, run_full_demo


def main():
    parser = argparse.ArgumentParser(description="PyPrep Pro job preparation platform")
    parser.add_argument(
        "--mode", choices=("gui", "cli", "tui", "api", "demo", "tests", "admin-setup"),
        default="gui", help="Application mode (default: gui)",
    )
    parser.add_argument("--host", default=API_HOST, help="API bind host")
    parser.add_argument("--port", type=int, default=API_PORT, help="API bind port")
    parser.add_argument("--database", default=str(DATABASE_PATH), help="SQLite database file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.mode == "tests":
        suite = unittest.defaultTestLoader.discover("tests")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())

    if args.mode == "gui":
        environment = os.environ.copy()
        environment["PYPREP_DATABASE"] = args.database
        raise SystemExit(subprocess.call(
            [sys.executable, "-m", "streamlit", "run",
             str(BASE_DIR / "ui" / "streamlit_app.py")],
            cwd=BASE_DIR,
            env=environment,
        ))

    container = PlatformContainer(args.database)
    try:
        if args.mode == "api":
            with make_server(args.host, args.port, FlaskCompatRouter(container)) as server:
                print(f"PyPrep Pro API listening on http://{args.host}:{args.port}")
                server.serve_forever()
        elif args.mode == "demo":
            run_full_demo(container)
        elif args.mode == "tui":
            run_curses_tui(container)
        elif args.mode == "admin-setup":
            password = getpass.getpass("New admin password (at least 8 characters): ")
            container.auth.ensure_admin(ADMIN_EMAIL, "Platform Admin", password)
            print(f"Admin account ready: {ADMIN_EMAIL}")
        else:
            TerminalCLI(container).run()
    finally:
        container.close()


if __name__ == "__main__":
    main()
