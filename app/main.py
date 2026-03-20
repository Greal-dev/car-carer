import logging

# ── Structured logging (configured before anything else) ──────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.database import Base, engine
from app.routers import auth, vehicles, documents, chat

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Care of your Car", version="0.1.0")

# API routes
app.include_router(auth.router)
app.include_router(vehicles.router)
app.include_router(documents.router)
app.include_router(chat.router)


# ── Inline migrations ─────────────────────────────────────────────────
# SQLite has limited ALTER TABLE support, making Alembic impractical for
# adding columns to existing tables.  These migrations run at startup
# and are idempotent: each ALTER TABLE is wrapped in a try/except so
# that an already-existing column is silently skipped.
def _run_migrations():
    import sqlalchemy

    insp = sqlalchemy.inspect(engine)
    if "vehicles" not in insp.get_table_names():
        return

    cols = [c["name"] for c in insp.get_columns("vehicles")]

    with engine.begin() as conn:
        if "user_id" not in cols:
            try:
                conn.execute(sqlalchemy.text(
                    "ALTER TABLE vehicles ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))
                logger.info("Migration applied: vehicles.user_id added")
            except Exception:
                logger.info("Migration skipped: vehicles.user_id already exists")

        if "photo_path" not in cols:
            try:
                conn.execute(sqlalchemy.text(
                    "ALTER TABLE vehicles ADD COLUMN photo_path VARCHAR(255)"
                ))
                logger.info("Migration applied: vehicles.photo_path added")
            except Exception:
                logger.info("Migration skipped: vehicles.photo_path already exists")


_run_migrations()


# Static files (frontend)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(str(static_dir / "index.html"))
