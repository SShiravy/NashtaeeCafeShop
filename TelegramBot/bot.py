from re import escape
from warnings import filterwarnings

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from TelegramBot import handlers
from TelegramBot import keyboards

# Expected: with per_message=False, callback queries are tracked per chat/user, which is what we want.
filterwarnings("ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

TEXT = filters.TEXT & ~filters.COMMAND


def _callback(callback, data: str, prefix: bool = False) -> CallbackQueryHandler:
    return CallbackQueryHandler(
        callback, pattern=f"^{escape(data)}" + ("" if prefix else "$")
    )


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
    ]
    return ConversationHandler(
        entry_points=[CommandHandler("start", handlers.start), *navigation],
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
            handlers.NAME: [MessageHandler(TEXT, handlers.get_name)],
            handlers.COMPANY: [MessageHandler(TEXT, handlers.get_company)],
            handlers.PHONE: [
                MessageHandler(filters.CONTACT | TEXT, handlers.get_phone)
            ],
            handlers.ADDRESS: [MessageHandler(TEXT, handlers.get_address)],
            handlers.CONFIRM: [
                _callback(handlers.confirm_order, keyboards.CONFIRM),
                _callback(handlers.edit_order, keyboards.EDIT),
                _callback(handlers.cancel_order, keyboards.CANCEL),
            ],
        },
        fallbacks=[CommandHandler("cancel", handlers.cancel_command)],
        allow_reentry=True,
    )


async def _set_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [BotCommand("start", "شروع سفارش"), BotCommand("cancel", "لغو سفارش")]
    )


def build_application(
    token: str, admin_id: int | str, proxy: str | None = None
) -> Application:
    """admin_id: chat that receives every confirmed order."""
    builder = Application.builder().token(token).post_init(_set_commands)
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
    app = builder.build()
    app.bot_data["admin_id"] = admin_id

    app.add_handler(build_conversation())
    # Reached only when the conversation didn't handle the update.
    app.add_handler(CallbackQueryHandler(handlers.expired_button))
    app.add_handler(MessageHandler(TEXT, handlers.use_buttons))
    app.add_error_handler(handlers.on_error)
    return app
