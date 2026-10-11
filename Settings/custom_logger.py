import logging
import colorlog
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Optional
from pathlib import Path
import threading
import requests


class TelegramLogHandler(logging.Handler):
    """Sends log records to a Telegram chat via bot API. Fire-and-forget, non-blocking."""

    def __init__(self, bot_token: str, chat_id: int | str, level: int = logging.NOTSET):
        super().__init__(level)
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        threading.Thread(target=self._send, args=(message,), daemon=True).start()

    def _send(self, message: str) -> None:
        try:
            requests.post(
                self._url,
                data={"chat_id": self._chat_id, "text": message},
                timeout=5,
            )
        except requests.RequestException:
            logging.warning("can not send log to channel")


def console_handler(level: int) -> logging.Handler:
    formatter = colorlog.ColoredFormatter(
        "{log_color}#{asctime}# {name}:\n --*{levelname}*->|[{message}]|\n",
        style="{",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "white",
            "INFO": "cyan",
            "WARNING": "yellow",
            "ERROR": "bold_red",
            "CRITICAL": "bold_purple",
        },
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def file_handler(level: int, name: str, dir: Path) -> logging.Handler:
    dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "#{asctime}#{name}# --*{levelname}*->|[{message}]|",
        style="{",
        datefmt="%D;%H:%M:%S",
    )
    handler = RotatingFileHandler(
        filename=dir / f"{name}.log",
        mode="a",
        encoding="utf-8",
        maxBytes=int(1e6),
        backupCount=1,
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


class TelegramFormatter(logging.Formatter):
    DEFAULT_STICKERS = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "🚫",
        "CRITICAL": "🔥",
    }

    def __init__(self, stickers: dict | None = None):
        super().__init__(
            "{asctime}\n{levelname}\n{emoji}\n{message}",
            style="{",
            datefmt="%D;%H:%M:%S",
        )
        self.stickers = stickers or self.DEFAULT_STICKERS

    def format(self, record: logging.LogRecord) -> str:
        record.emoji = self.stickers.get(record.levelname, "📌")
        return super().format(record)


def telegram_handler(level: int, bot_token: str, chat_id: int | str) -> logging.Handler:
    handler = TelegramLogHandler(bot_token=bot_token, chat_id=chat_id, level=level)
    handler.setFormatter(TelegramFormatter())
    return handler


@dataclass
class LoggerConfig:
    name: str = "app"
    console: bool = True
    console_level: int = logging.DEBUG
    log_file_name: Optional[str] = None
    log_dir: Path = Path("Logs")
    file_level: int = logging.INFO
    telegram_token: Optional[str] = None
    telegram_channel: str | int | None = None
    telegram_level: int = logging.WARNING
    extra_handlers: list = field(default_factory=list)


def build_logger(config: LoggerConfig) -> logging.Logger:
    logger = logging.getLogger(config.name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    if config.console:
        logger.addHandler(console_handler(config.console_level))
    if config.log_file_name:
        logger.addHandler(
            file_handler(config.file_level, config.log_file_name, config.log_dir)
        )
    if config.telegram_token and config.telegram_channel:
        logger.addHandler(
            telegram_handler(
                config.telegram_level, config.telegram_token, config.telegram_channel
            )
        )
    for handler in config.extra_handlers:
        logger.addHandler(handler)

    return logger


logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("matplotlib.category").setLevel(logging.WARNING)
logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
logging.getLogger("matplotlib.pyplot").setLevel(logging.WARNING)


if __name__ == "__main__":
    from Settings.config import settings

    logger = build_logger(
        LoggerConfig(
            name="root",
            log_file_name="test",
            telegram_channel=settings.TELEGRAM_REPORT_CHANNEL,
            telegram_token=settings.TELEGRAM_CUSTOMER_BOT_TOKEN,
        )
    )
    logger.debug("mio")
    logger.info("mio")
    logger.warning("mio")
    logger.error("mio")
    logger.critical("mio")
    logger.exception("mio")

    import logging

    logging.warning("1")
    logging.info("2")
    logging.debug("3")
    logging.error("4")
    logging.critical("5")

    other_logger = logging.getLogger("test_not_root")
    other_logger.error("not roooooottt")
    import time

    time.sleep(3)
