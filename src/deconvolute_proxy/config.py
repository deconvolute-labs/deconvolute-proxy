import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    github_token: str
    deconvolute_cache_dir: str = "./data/"
    host: str = "127.0.0.1"
    port: int = 8000
    policy_path: str = "policy.yaml"
    deconvolute_api_key: str | None = None
    agent_id: str | None = None


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
