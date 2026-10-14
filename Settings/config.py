from pydantic import NonNegativeInt, PositiveInt
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

    # Referral plan (Models.referral.ReferralPlan), discounts in toman
    REFERRAL_FIRST_BUY_DISCOUNT: NonNegativeInt = 10_000  # d: invited user's 1st order
    REFERRAL_REWARD_EVERY: PositiveInt = 1  # n: invited users per reward
    REFERRAL_REWARD_DISCOUNT: NonNegativeInt = 20_000  # m: inviter's reward
    # False: invited users count toward a reward as soon as they join, not once they buy
    REFERRAL_REWARD_ON_PURCHASE: bool = True

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()  # type: ignore
