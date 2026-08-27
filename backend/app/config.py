from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


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


settings = Settings()
