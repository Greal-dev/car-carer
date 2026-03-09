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


# Migrate existing DB: add missing columns
def _migrate_db():
    import sqlalchemy
    insp = sqlalchemy.inspect(engine)
    if "vehicles" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("vehicles")]
        with engine.begin() as conn:
            if "user_id" not in cols:
                conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN user_id INTEGER REFERENCES users(id)"))
            if "photo_path" not in cols:
                conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN photo_path VARCHAR(255)"))

_migrate_db()


# Static files (frontend)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(str(static_dir / "index.html"))


