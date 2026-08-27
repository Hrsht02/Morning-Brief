from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app configuration, loaded from environment variables / .env file.
    Every external credential lives here and ONLY here - never hardcode a key
    anywhere else in the codebase.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./morning_brief.db"

    JWT_SECRET_KEY: str = "insecure-default-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"

    # Independent second-opinion verifier - deliberately a DIFFERENT provider
    # from Groq (per the multi-layer verification design), so the generator
    # and verifier are never the same model/account checking its own work.
    # Free tier, no credit card: https://aistudio.google.com/apikey
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"

    # Google Sign-In (both user and admin login). Create a free OAuth Client ID
    # at https://console.cloud.google.com/apis/credentials - "Web application"
    # type, add your frontend URL under Authorized JavaScript origins.
    GOOGLE_CLIENT_ID: str = ""

    BREVO_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "news@example.com"
    EMAIL_FROM_NAME: str = "Morning Brief"

    CRON_SECRET: str = "insecure-default-change-me"

    FRONTEND_URL: str = "http://localhost:5173"

    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "admin123"


settings = Settings()
