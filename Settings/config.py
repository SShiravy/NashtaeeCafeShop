from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    def __new__(cls):
        if not hasattr(cls, "__instance"):
            cls.__instance = object.__new__(cls)
        return cls.__instance

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_REPORT_CHANNEL: int

    # Database
    DB_NAME: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore
