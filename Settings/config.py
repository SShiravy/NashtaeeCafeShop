from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    def __new__(cls):
        if not hasattr(cls, "__instance"):
            cls.__instance = object.__new__(cls)
        return cls.__instance

    # Telegram Bot
    TELEGRAM_CUSTOMER_BOT_TOKEN: str
    TELEGRAM_ADMIN_ID: int
    TELEGRAM_SUPPORT_ID: str
    TELEGRAM_REPORT_CHANNEL: str
    TELEGRAM_PROXY: str | None = None  # e.g. socks5://127.0.0.1:9050

    # Database
    DB_NAME: str

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore
