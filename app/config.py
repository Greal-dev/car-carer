import secrets
import logging

from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path, override=True)

# Auto-generate JWT_SECRET in .env if missing
_has_jwt_secret = False
if _env_path.exists():
    _has_jwt_secret = any(
        line.startswith("JWT_SECRET=")
        for line in _env_path.read_text().splitlines()
        if line.strip()
    )

if not _has_jwt_secret:
    _secret = secrets.token_hex(32)
    with open(_env_path, "a") as f:
        f.write(f"\nJWT_SECRET={_secret}\n")
    load_dotenv(_env_path, override=True)
    logger.info("Generated new JWT_SECRET and appended to .env")


class Settings(BaseSettings):
    anthropic_api_key: str
    openrouter_api_key: str
    database_url: str = "sqlite:///./care.db"
    jwt_secret: str = ""

    # Externalized config (overridable via .env)
    jwt_expire_hours: int = 72
    batch_max_concurrent: int = 3
    batch_max_files: int = 100
    extraction_timeout: int = 60
    extraction_model: str = "google/gemini-2.5-flash"
    max_photo_size_mb: int = 10
    upload_dir: str = "./uploads"


settings = Settings()

UPLOAD_PATH = Path(settings.upload_dir)
UPLOAD_PATH.mkdir(parents=True, exist_ok=True)
