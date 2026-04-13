from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Core
    environment: str = "development"
    port: int = 8000

    # Database
    mongodb_url: str = "mongodb://localhost:27017/agent_arena"
    redis_url: str = "redis://localhost:6379"

    # External APIs
    anthropic_api_key: str = ""
    news_api_key: str = ""  # TODO: Get from https://newsapi.org
    cricapi_key: str = ""    # TODO: Get from https://cricapi.com

    # Auth
    jwt_secret: str = "change-me-in-production-use-32-chars-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    # CORS
    frontend_url: str = "http://localhost:5173"
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # LLM
    llm_model: str = "claude-sonnet-4-5"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    # Email — Resend (resend.com, free 3k/mo) takes priority.
    # Fallback: Gmail SMTP — enable 2FA, generate an App Password at
    # https://myaccount.google.com/apppasswords, then set SMTP_USER + SMTP_PASS.
    resend_api_key: str = ""
    email_from: str = "noreply@agentarena.app"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""   # your Gmail address
    smtp_pass: str = ""   # 16-char Gmail App Password

    # Rate limiting
    prediction_rate_limit: int = 10  # per agent per hour

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
