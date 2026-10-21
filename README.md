# PyPrep Pro

PyPrep Pro is a job and competitive-exam preparation platform with a browser-based graphical interface, terminal menus, and a JSON WSGI API. The graphical interface uses Streamlit; platform data is stored in SQLite.

## Requirements and setup

- Python 3.10 or newer
- Install the application dependencies: `python -m pip install -r requirements.txt`
- On Windows, install `windows-curses` to use `--mode tui` (included in the requirements file).

From this directory:

```powershell
python run.py
```

This opens the graphical interface in your browser. The application creates `pyprep.db` and loads sample data on first run. To choose a different SQLite database:

```powershell
python run.py --database .\data\practice.db
```

### Admin account

Create or promote the configured admin account by setting `PYPREP_ADMIN_EMAIL` and `PYPREP_ADMIN_PASSWORD` before startup. Alternatively, run the interactive setup command, which prompts for a password and uses `PYPREP_ADMIN_EMAIL` (default `admin@example.com`):

```powershell
python run.py --mode admin-setup
```

There is no default admin password. Passwords are stored as PBKDF2-HMAC-SHA256 hashes. Bearer sessions expire after 24 hours by default; configure `PYPREP_SESSION_TTL_HOURS` and `PYPREP_PASSWORD_ITERATIONS` to adjust those settings.

## Modes

```powershell
python run.py --mode gui       # Browser-based graphical interface (default)
python run.py --mode cli       # Interactive account, exam, interview, and contribution menus
python run.py --mode tui       # Optional arrow-key curses catalog/menu
python run.py --mode api       # JSON API at http://127.0.0.1:8000
python run.py --mode demo      # Automated seeded showcase
python run.py --mode tests     # unittest suite
```

For the API, configure `PYPREP_API_HOST`, `PYPREP_API_PORT`, or pass `--host`/`--port`. Keep the bind host on loopback unless the API is deployed behind an appropriately secured network boundary; the built-in WSGI server is intended for development/small local deployments.

## Features

- Registration, login, PBKDF2 password hashing, bearer-session expiry, and student/admin role checks.
- Five seeded exam categories (TCS NQT, SSC CGL, UPSC CSAT, TCS BPS, and Core Technical), with 30 multiple-choice questions, timed attempts, negative marking, answer review, and topic/difficulty analytics.
- HR and technical interview scenarios with rubric-based feedback and a confidence history.
- Student question/solution submissions, admin moderation, and 1–5-star peer reviews for approved contributions.
- Admin user-role management, exam/question creation, moderation queue, and usage dashboard.
- SQLite persistence with foreign-key enforcement and transaction-safe test submission/seeding.

## API

All request and response bodies are JSON. Protected routes use `Authorization: Bearer <token>`. Successful resource creation returns `201`; invalid input returns `400`; authentication/authorization errors return `401`/`403`.

| Method | Route | Access | Purpose |
|---|---|---|---|
| GET | `/api/health` | Public | Health check |
| POST | `/api/register` | Public | Register a student (`email`, `name`, `password`) |
| POST | `/api/login` | Public | Sign in and receive bearer token |
| POST | `/api/logout` | Student/admin | Revoke current session |
| GET | `/api/exams` | Public | List exams |
| POST | `/api/tests` | Student | Start attempt (`exam_id`) |
| GET | `/api/tests/<id>` | Student | Read attempt questions and deadline |
| POST | `/api/tests/<id>/submit` | Student | Submit `{ "answers": { "<question_id>": "<option>" } }` |
| GET | `/api/tests/history` | Student | Read own attempts |
| GET | `/api/interviews?category=HR` | Student | List scenarios (category optional) |
| POST | `/api/interviews/practice` | Student | Submit `scenario_id`, `answer`, `confidence` (1–5) |
| GET | `/api/interviews/confidence` | Student | Read confidence history |
| GET/POST | `/api/contributions` | Student | Browse approved contributions / submit a contribution |
| POST | `/api/contributions/<id>/reviews` | Student | Rate an approved contribution |
| GET | `/api/admin/dashboard` | Admin | Usage KPIs |
| GET | `/api/admin/users` | Admin | List users |
| PATCH | `/api/admin/users/<id>` | Admin | Set `role` to `student` or `admin` |
| DELETE | `/api/admin/users/<id>` | Admin | Delete a user (cannot delete the current admin) |
| GET | `/api/admin/contributions` | Admin | List pending submissions |
| POST | `/api/admin/contributions/<id>/moderate` | Admin | Set status to `approved` or `rejected` |
| POST | `/api/admin/exams` | Admin | Create exam |
| PUT/DELETE | `/api/admin/exams/<id>` | Admin | Update exam / delete exam without test history |
| POST | `/api/admin/questions` | Admin | Add a question |

## Extending the dataset

Edit `data/sample_exam_dataset.json`. Each exam has a unique name, category, duration, negative-marking value, and question list. Questions include topic, difficulty (`easy`, `medium`, `hard`), prompt, options, correct answer, and optional explanation. The first-run seeder populates an empty database only; changing the JSON does not overwrite an existing database.

## Tests

```powershell
python run.py --mode tests
```
