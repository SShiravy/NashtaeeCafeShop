import logging
from datetime import datetime, time
from re import escape
from warnings import filterwarnings

from telegram import BotCommand, BotCommandScopeChat, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from TelegramBot import handlers
from TelegramBot import keyboards
from TelegramBot.PanelAdmin import handlers as admin
from TelegramBot.PanelAdmin import keyboards as admin_keyboards

log = logging.getLogger(__name__)

# Expected: with per_message=False, callback queries are tracked per chat/user, which is what we want.
filterwarnings("ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

TEXT = filters.TEXT & ~filters.COMMAND


def _pattern(data: str, prefix: bool) -> str:
    return f"^{escape(data)}" + ("" if prefix else "$")


def _callback(callback, data: str, prefix: bool = False) -> CallbackQueryHandler:
    return CallbackQueryHandler(callback, pattern=_pattern(data, prefix))


def build_conversation() -> ConversationHandler:
    # Menu and cart buttons are entry points, and allow_reentry lets them interrupt
    # any step, so they keep working mid-checkout and after an order is finished.
    navigation = [
        _callback(handlers.show_main_menu, keyboards.MAIN),
        _callback(handlers.show_category, keyboards.CATEGORY_PREFIX, prefix=True),
        _callback(handlers.show_item, keyboards.ITEM_PREFIX, prefix=True),
        _callback(handlers.choose_quantity, keyboards.QTY_PREFIX, prefix=True),
        _callback(
            handlers.ask_custom_quantity, keyboards.CUSTOM_QTY_PREFIX, prefix=True
        ),
        _callback(handlers.show_cart, keyboards.CART),
        _callback(handlers.clear_cart, keyboards.CART_CLEAR),
        _callback(handlers.checkout, keyboards.CHECKOUT),
        _callback(handlers.start_new_order, keyboards.NEW_ORDER),
        _callback(handlers.show_profile, keyboards.PROFILE),
        _callback(handlers.ask_new_name, keyboards.PROFILE_NAME),
        _callback(handlers.ask_new_company, keyboards.PROFILE_COMPANY),
        _callback(handlers.ask_new_phone, keyboards.PROFILE_PHONE),
        _callback(handlers.open_poll, keyboards.POLL),
        _callback(handlers.answer_poll, keyboards.POLL_ANSWER_PREFIX, prefix=True),
        _callback(
            handlers.show_poll_question, keyboards.POLL_QUESTION_PREFIX, prefix=True
        ),
        _callback(handlers.skip_poll_question, keyboards.POLL_SKIP_PREFIX, prefix=True),
    ]
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", handlers.start),
            CommandHandler("profile", handlers.show_profile),
            CommandHandler("poll", handlers.open_poll),
            *navigation,
        ],
        states={
            handlers.MENU: [],  # only the navigation entry points apply here
            handlers.CUSTOM_QTY: [
                MessageHandler(TEXT, handlers.receive_custom_quantity)
            ],
            handlers.RECEIVE: [
                _callback(
                    handlers.choose_receive_method,
                    keyboards.RECEIVE_PREFIX,
                    prefix=True,
                )
            ],
            handlers.NAME: [
                MessageHandler(TEXT, handlers.get_name),
                _callback(handlers.back_to_summary, keyboards.SUMMARY),
            ],
            handlers.COMPANY: [
                MessageHandler(TEXT, handlers.get_company),
                _callback(handlers.back_to_summary, keyboards.SUMMARY),
            ],
            handlers.PHONE: [
                MessageHandler(filters.CONTACT | TEXT, handlers.get_phone)
            ],
            handlers.ADDRESS: [
                MessageHandler(TEXT, handlers.get_address),
                _callback(
                    handlers.choose_address, keyboards.ADDRESS_PREFIX, prefix=True
                ),
                _callback(handlers.ask_new_address, keyboards.ADDRESS_NEW),
                _callback(handlers.show_addresses, keyboards.ADDRESS_LIST),
            ],
            handlers.CONFIRM: [
                _callback(handlers.confirm_order, keyboards.CONFIRM),
                _callback(handlers.edit_order, keyboards.EDIT),
                _callback(handlers.cancel_order, keyboards.CANCEL),
                _callback(handlers.edit_receive_method, keyboards.EDIT_RECEIVE),
                _callback(handlers.ask_new_name, keyboards.EDIT_NAME),
                _callback(handlers.ask_new_company, keyboards.EDIT_COMPANY),
                _callback(handlers.ask_new_phone, keyboards.EDIT_PHONE),
                _callback(handlers.back_to_summary, keyboards.SUMMARY),
            ],
            handlers.POLL_TEXT: [MessageHandler(TEXT, handlers.receive_poll_text)],
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_command)],
        allow_reentry=True,
    )


class _AdminCallbackHandler(CallbackQueryHandler):
    """A CallbackQueryHandler that only matches buttons pressed in the admin chat."""

    def __init__(self, admin_id: int, callback, pattern: str):
        super().__init__(callback, pattern=pattern)
        self.admin_id = admin_id

    def check_update(self, update: object):
        if not isinstance(update, Update) or update.effective_chat is None:
            return None
        if update.effective_chat.id != self.admin_id:
            return None
        return super().check_update(update)


def _stop_after(callback):
    """Keep a handled admin update from also reaching the customer handlers."""

    async def wrapper(update: Update, context) -> None:
        raise ApplicationHandlerStop(await callback(update, context))

    return wrapper


def build_admin_conversation(admin_id: int) -> ConversationHandler:
    """Products and open orders panel, opened with /admin; for handler group -1."""

    def button(callback, data: str, prefix: bool = False) -> CallbackQueryHandler:
        return _AdminCallbackHandler(
            admin_id, _stop_after(callback), _pattern(data, prefix)
        )

    def text(callback) -> MessageHandler:
        return MessageHandler(TEXT, _stop_after(callback))

    # As on the customer side, navigation buttons are entry points so they work
    # from every step; Cancel buttons on text prompts are navigation too.
    navigation = [
        CommandHandler(
            "admin", _stop_after(admin.open_panel), filters=filters.Chat(admin_id)
        ),
        button(admin.show_panel, admin_keyboards.HOME),
        button(admin.show_category, admin_keyboards.CATEGORY_PREFIX, prefix=True),
        button(admin.show_product, admin_keyboards.PRODUCT_PREFIX, prefix=True),
        button(admin.toggle_available, admin_keyboards.TOGGLE_PREFIX, prefix=True),
        button(admin.ask_edit, admin_keyboards.EDIT_PREFIX, prefix=True),
        button(admin.ask_delete, admin_keyboards.DELETE_PREFIX, prefix=True),
        button(
            admin.delete_product, admin_keyboards.DELETE_CONFIRM_PREFIX, prefix=True
        ),
        button(admin.new_product, admin_keyboards.NEW),
        button(admin.show_open_orders, admin_keyboards.ORDERS),
        # Order buttons return None, so they leave any panel input as it was.
        button(admin.finish_order, admin_keyboards.ORDER_FINISH_PREFIX, prefix=True),
        button(
            admin.ask_cancel_order, admin_keyboards.ORDER_CANCEL_PREFIX, prefix=True
        ),
        button(
            admin.cancel_order, admin_keyboards.ORDER_CANCEL_CONFIRM_PREFIX, prefix=True
        ),
        button(
            admin.show_order_actions, admin_keyboards.ORDER_ACTIONS_PREFIX, prefix=True
        ),
    ]
    return ConversationHandler(
        entry_points=navigation,
        states={
            admin.IDLE: [],  # only the navigation entry points apply here
            admin.EDIT_FIELD: [text(admin.receive_edit)],
            admin.NEW_NAME: [text(admin.receive_new_name)],
            admin.NEW_FARSI_NAME: [text(admin.receive_new_farsi_name)],
            admin.NEW_NUMBER: [text(admin.receive_new_number)],
            admin.NEW_CATEGORY: [
                button(
                    admin.receive_new_category,
                    admin_keyboards.NEW_CATEGORY_PREFIX,
                    prefix=True,
                )
            ],
            admin.NEW_CONFIRM: [
                button(admin.save_new_product, admin_keyboards.NEW_SAVE)
            ],
        },
        # Leaving for the customer side (or the order buttons) ends the panel
        # input; these don't stop the update, so the customer handlers still run.
        fallbacks=[
            CommandHandler(["start", "cancel", "profile", "poll"], admin.leave_panel),
            CallbackQueryHandler(admin.leave_panel, pattern=r"^(?!adm:)"),
        ],
        allow_reentry=True,
    )


BACKUP_TIME = time(23, 55)

CUSTOMER_COMMANDS = [
    BotCommand("start", "شروع سفارش"),
    BotCommand("cancel", "لغو سفارش"),
    BotCommand("support", "پشتیبانی"),
    BotCommand("profile", "اطلاعات من"),
    BotCommand("poll", "شرکت در نظرسنجی"),
]

# Shown in an empty chat with the bot, before the user presses Start.
DESCRIPTION = "ناشتایی، شروع خوبِ روز توعه"


async def _set_bot_info(app: Application) -> None:
    """The description and the command menu; Telegram keeps them between restarts."""
    await app.bot.set_my_description(DESCRIPTION)
    await app.bot.set_my_commands(CUSTOMER_COMMANDS)
    try:
        await app.bot.set_my_commands(
            [
                *CUSTOMER_COMMANDS,
                BotCommand("admin", "پنل مدیریت"),
                BotCommand("backup", "بک اپ دیتابیس"),
            ],
            scope=BotCommandScopeChat(app.bot_data["admin_id"]),
        )
    except TelegramError:
        log.warning(
            "Could not set the admin's commands; has the admin started the bot?"
        )


def build_application(
    token: str, admin_id: int | str, proxy: str | None = None, support_id: str = ""
) -> Application:
    """admin_id: chat that approves or rejects every order and manages products.
    support_id: what /support sends customers, e.g. an @username.
    """
    builder = Application.builder().token(token).post_init(_set_bot_info)
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
    app = builder.build()
    app.bot_data["admin_id"] = admin_id
    app.bot_data["support_id"] = support_id

    app.add_handler(build_admin_conversation(int(admin_id)), group=-1)
    app.add_handler(
        CommandHandler(
            "backup", admin.backup_command, filters=filters.Chat(int(admin_id))
        ),
        group=-1,
    )
    app.job_queue.run_daily(
        admin.send_backup,
        # The server's own timezone, so "end of the day" is the cafe's evening.
        BACKUP_TIME.replace(tzinfo=datetime.now().astimezone().tzinfo),
        name="daily_backup",
    )
    app.add_handler(build_conversation())
    # The conversation doesn't handle /support, so it reaches this in any step.
    app.add_handler(CommandHandler("support", handlers.support))
    app.add_handler(
        _callback(handlers.admin_confirm, keyboards.ADMIN_CONFIRM_PREFIX, prefix=True)
    )
    app.add_handler(
        _callback(handlers.admin_cancel, keyboards.ADMIN_CANCEL_PREFIX, prefix=True)
    )
    # Reached only when the conversation didn't handle the update.
    app.add_handler(CallbackQueryHandler(handlers.expired_button))
    app.add_handler(MessageHandler(TEXT, handlers.use_buttons))
    app.add_error_handler(handlers.on_error)
    return app
