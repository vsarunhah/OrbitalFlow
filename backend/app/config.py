from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://jobtracker:jobtracker@localhost:5432/jobtracker"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    debug: bool = False  # If True, 500 responses include exception message (dev only)
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"
    app_encryption_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/email-accounts/gmail/oauth-callback"

    # Password reset (optional: if not set, reset link is logged only)
    frontend_base_url: str = "http://localhost:3000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    password_reset_expire_minutes: int = 60

    sync_poll_interval_seconds: int = 300
    sync_lookback_minutes: int = 30
    rq_job_timeout: int = 600
    rq_retry_max: int = 3
    rq_retry_delay: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
