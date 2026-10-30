from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    database_url_admin: str
    jwt_secret: str
    worker_id_pepper: str
    monolith_url: str = "http://monolith:8001"
    env: str = "dev"
    log_level: str = "INFO"
    pool_size: int = 3
    max_overflow: int = 2


settings = Settings()
