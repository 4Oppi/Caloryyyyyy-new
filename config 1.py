from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    BOT_TOKEN: str
    GEMINI_API_KEY: str
    JWT_SECRET: str = "nutrios-secret-change-in-production"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
