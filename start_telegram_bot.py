from Database import create_db_and_tables
from Models.referral import ReferralPlan
from Settings import LoggerConfig, build_logger, settings
from TelegramBot import build_application


def main() -> None:
    logger = build_logger(
        LoggerConfig(
            name="TelegramBot",
            log_file_name="telegram_bot",
            telegram_token=settings.TELEGRAM_CUSTOMER_BOT_TOKEN,
            telegram_channel=settings.TELEGRAM_REPORT_CHANNEL,
        )
    )
    create_db_and_tables()
    logger.info(
        "Starting Nashtaee bot%s", " via proxy" if settings.TELEGRAM_PROXY else ""
    )
    build_application(
        settings.TELEGRAM_CUSTOMER_BOT_TOKEN,
        admin_id=settings.TELEGRAM_ADMIN_ID,
        proxy=settings.TELEGRAM_PROXY,
        support_id=settings.TELEGRAM_SUPPORT_ID,
        referral_plan=ReferralPlan(
            first_buy_discount=settings.REFERRAL_FIRST_BUY_DISCOUNT,
            reward_every=settings.REFERRAL_REWARD_EVERY,
            reward_discount=settings.REFERRAL_REWARD_DISCOUNT,
            reward_on_purchase=settings.REFERRAL_REWARD_ON_PURCHASE,
        ),
    ).run_polling()


if __name__ == "__main__":
    main()
