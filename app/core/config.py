from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Hackersquad AI Marketing Agent"
    api_prefix: str = ""
    database_url: str = "sqlite://"
    uploads_dir: str = "./uploads"
    heartbeat_interval_seconds: int = 20
    stale_timeout_seconds: int = 75
    max_retries: int = 3
    model_provider: str = "single-provider"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_vision_model: str = "gpt-4.1-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
