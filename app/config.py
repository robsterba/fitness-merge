from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://fitness:fitness@localhost:5432/fitness"
    import_dir: str = "./imports"

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/auth/strava/callback"
    public_base_url: str = "http://localhost:8000"

    # Matching heuristics (same workout across sources)
    match_start_tolerance_seconds: int = 15 * 60
    match_duration_tolerance_ratio: float = 0.12


@lru_cache
def get_settings() -> Settings:
    return Settings()
