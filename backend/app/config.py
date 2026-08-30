from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def resolve_sqlite_url(database_url: str) -> str:
    """Anchor a relative sqlite:/// URL to backend/, so the database is
    always the same file regardless of the current working directory the
    process happened to start from (running a script from scripts/ instead
    of backend/ would otherwise silently create a fresh, empty database).
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return database_url
    raw_path = Path(database_url[len(prefix) :])
    if raw_path.is_absolute():
        return database_url
    return f"{prefix}{(BACKEND_ROOT / raw_path).resolve().as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    kalshi_key_id: str = ""
    kalshi_private_key_path: str = "./kalshi_private.pem"
    kalshi_api_base_url: str = "https://external-api.kalshi.com"
    kalshi_live_test_enabled: bool = False

    database_url: str = "sqlite:///./app.db"

    apify_api_token: str = ""
    apify_news_actor_id: str = "apify/website-content-crawler"

    polymarket_api_base_url: str = "https://gamma-api.polymarket.com"

    edge_margin_threshold: float = 0.02
    max_position_pct_of_bankroll: float = 0.03
    kelly_fraction_cap: float = 0.5

    paper_bankroll_usd: float = 1000.0

    btc_15min_position_size_usd: float = 20.0
    btc_15min_profit_target_pct: float = 0.15
    btc_15min_poll_seconds: float = 5.0
    btc_15min_entry_window_seconds: float = 60.0


settings = Settings()
