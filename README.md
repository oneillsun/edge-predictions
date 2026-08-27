# Edge Predictions

Kalshi + Apify trading bot. See `PLAN.md` for the milestone-by-milestone build
plan and `CLAUDE_1.md` for working conventions.

## Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Serves `/healthz` at `http://localhost:8000/healthz`.

Create the local database schema (SQLite by default, via `DATABASE_URL`):

```
cd backend
alembic upgrade head
```

Run this after pulling changes that add new migrations. To generate a new
migration after changing `app/db/models.py`:

```
alembic revision --autogenerate -m "describe the change"
```

Run tests:

```
cd backend
pytest
```

## Frontend

```
cd frontend
npm install
npm run dev
```

Serves the placeholder dashboard at `http://localhost:5173`.

## Environment

Copy `.env.example` to `.env` and fill in values before running Milestone 1+.
Never commit `.env` or any `*.pem` file.
