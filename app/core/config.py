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
    api_key: str = ""
    require_tenant_header: bool = False
    openai_api_key: str = ""
    openai_image_api_key: str = ""
    openai_video_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_vision_model: str = "gpt-4.1-mini"
    openai_image_model: str = "dall-e-2"
    openai_video_model: str = "sora-2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
