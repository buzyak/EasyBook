from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    bot_token: str
    owner_telegram_id: int
    public_base_url: str = "http://localhost:8000"
    secret_key: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./data/easybook.db"
    hold_minutes: int = 15
    timezone: str = "Europe/Moscow"
    dev_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
