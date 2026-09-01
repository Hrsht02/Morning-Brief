from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only configuration. Secrets are never stored in source."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite:///./morning_brief.db"
    JWT_SECRET_KEY: str = "insecure-default-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GOOGLE_CLIENT_ID: str = ""
    BREVO_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "news@example.com"
    EMAIL_FROM_NAME: str = "Morning Brief"
    CRON_SECRET: str = "insecure-default-change-me"
    ADMIN_DIAGNOSTICS_KEY: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "admin123"

    def validate_production(self):
        if self.ENVIRONMENT.lower() not in {"production", "prod"}:
            return
        weak = {"insecure-default-change-me", "admin123", "change-this-password", "admin@example.com"}
        if self.JWT_SECRET_KEY in weak or self.CRON_SECRET in weak or self.ADMIN_PASSWORD in weak or self.ADMIN_EMAIL in weak:
            raise RuntimeError("Production configuration contains insecure default auth/admin values")


settings = Settings()
settings.validate_production()
