import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Cache-buster для статики (CSS/JS) — міняється при кожному рестарті процесу,
# інакше браузер тримає застарілий theme.css навіть після редагування файлу.
STATIC_VERSION = str(int(time.time()))


@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_string: str
    database_url: str
    redis_url: str
    admin_basic_auth_user: str
    admin_basic_auth_password: str


def load_settings() -> Settings:
    return Settings(
        telegram_api_id=int(os.environ["TELEGRAM_API_ID"]),
        telegram_api_hash=os.environ["TELEGRAM_API_HASH"],
        telegram_session_string=os.environ["TELEGRAM_SESSION_STRING"],
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        admin_basic_auth_user=os.environ["ADMIN_BASIC_AUTH_USER"],
        admin_basic_auth_password=os.environ["ADMIN_BASIC_AUTH_PASSWORD"],
    )
