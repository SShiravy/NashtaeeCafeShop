"""Admin panel for the TELEGRAM_ADMIN_ID chat: product CRUD and open orders.

Wired up in TelegramBot.bot.
"""

import logging
import re
from collections import Counter
from datetime import UTC, datetime

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from Database import repository
from Models.menu import Product, ProductCategory
from Models.order import Order, OrderState
from TelegramBot import keyboards as customer_keyboards
from TelegramBot.handlers import order_summary, pending_orders
from TelegramBot.PanelAdmin import keyboards
from TelegramBot.utils import en_digits, fa_digits, format_price

log = logging.getLogger(__name__)

# Conversation states
IDLE, EDIT_PRICE, NEW_NAME, NEW_FARSI_NAME, NEW_PRICE, NEW_CATEGORY, NEW_CONFIRM = (
    range(7)
)

MAX_PRICE = 1_000_000_000  # Toman
MAX_LISTED_ORDERS = 20  # one message each; more would hit Telegram's rate limits
NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,31}")

# chat_data keys; chat_data, because the customer side clears user_data on /start.
DRAFT = "admin_new_product"  # dict of Product fields while creating a product
EDITING = "admin_editing_product"  # Product.name whose price is being edited


# ---------- views ----------


def _panel_view() -> tuple[str, InlineKeyboardMarkup]:
    counts = Counter(p.category for p in repository.get_products(only_available=False))
    open_orders = len(repository.get_orders(OrderState.CONFIRMED))
    return (
        "🛠 پنل مدیریت ناشتایی\n\nسفارش‌های باز یا یک دسته محصولات را انتخاب کنید:",
        keyboards.panel(counts, open_orders),
    )


def _category_view(
    category: ProductCategory, note: str = ""
) -> tuple[str, InlineKeyboardMarkup]:
    products = [
        p
        for p in repository.get_products(only_available=False)
        if p.category == category
    ]
    lines = [note, ""] if note else []
    lines.append(category.value)
    lines.append(
        "\n🟢 موجود   🔴 ناموجود" if products else "\nمحصولی در این دسته نیست."
    )
    return "\n".join(lines), keyboards.category(products)


def _product_text(product: Product) -> str:
    return "\n".join(
        [
            f"🍽 {product.farsi_name}",
            f"🔤 شناسه: {product.name}",
            f"📂 دسته: {product.category.value}",
            f"💰 قیمت: {format_price(product.price)} تومان",
            f"📌 وضعیت: {'🟢 موجود' if product.available else '🔴 ناموجود'}",
        ]
    )


def _parse_price(text: str) -> int | None:
    """'۲۰۰٬۰۰۰' or '200,000' -> 200000; None if it isn't a sensible price."""
    digits = re.sub(r"[\s,٬،]", "", en_digits(text))
    if not digits.isdigit():
        return None
    price = int(digits)
    return price if 0 < price <= MAX_PRICE else None


async def _product_from_query(update: Update, prefix: str) -> Product | None:
    """The product named in the callback data, or None after telling the admin."""
    query = update.callback_query
    product = repository.get_product(
        query.data.removeprefix(prefix), only_available=False
    )
    if product is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
    return product


def _delete_blocker(context: ContextTypes.DEFAULT_TYPE, product: Product) -> str | None:
    """Why the product can't be deleted, or None if it can."""
    if repository.product_in_orders(product.name):
        return (
            "این محصول در سفارش‌های ثبت‌شده استفاده شده و قابل حذف نیست."
            " می‌توانید آن را ناموجود کنید."
        )
    waiting = pending_orders(context).values()
    if any(item.product.name == product.name for o in waiting for item in o.items):
        return "این محصول در سفارشی است که هنوز در انتظار تأیید است."
    return None


def _clear_input(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.pop(DRAFT, None)
    context.chat_data.pop(EDITING, None)


# ---------- navigation ----------


async def open_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/admin"""
    _clear_input(context)
    text, markup = _panel_view()
    await update.message.reply_text(text, reply_markup=markup)
    return IDLE


async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _clear_input(context)
    text, markup = _panel_view()
    await query.edit_message_text(text, reply_markup=markup)
    return IDLE


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    category = ProductCategory.__members__.get(
        query.data.removeprefix(keyboards.CATEGORY_PREFIX)
    )
    if category is None:
        await query.answer("این دسته پیدا نشد.", show_alert=True)
        return IDLE
    await query.answer()
    text, markup = _category_view(category)
    await query.edit_message_text(text, reply_markup=markup)
    return IDLE


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    product = await _product_from_query(update, keyboards.PRODUCT_PREFIX)
    if product is None:
        return IDLE
    _clear_input(context)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        _product_text(product), reply_markup=keyboards.product(product)
    )
    return IDLE


async def leave_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """The admin moved on to the customer side: drop any half-finished input."""
    _clear_input(context)
    return ConversationHandler.END


# ---------- update ----------


async def toggle_available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = await _product_from_query(update, keyboards.TOGGLE_PREFIX)
    if product is None:
        return IDLE
    product.available = not product.available
    repository.update_product(product)
    await query.answer("🟢 موجود شد." if product.available else "🔴 ناموجود شد.")
    await query.edit_message_text(
        _product_text(product), reply_markup=keyboards.product(product)
    )
    return IDLE


async def ask_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = await _product_from_query(update, keyboards.PRICE_PREFIX)
    if product is None:
        return IDLE
    context.chat_data[EDITING] = product.name
    await query.answer()
    await query.edit_message_text(
        f"💰 قیمت جدید «{product.farsi_name}» را به تومان وارد کنید:"
        f"\n(قیمت فعلی: {format_price(product.price)} تومان)",
        reply_markup=keyboards.cancel(keyboards.PRODUCT_PREFIX + product.name),
    )
    return EDIT_PRICE


async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = _parse_price(update.message.text)
    if price is None:
        await update.message.reply_text(
            "قیمت معتبر نیست. فقط عدد به تومان وارد کنید (مثلاً ۲۰۰۰۰۰):"
        )
        return EDIT_PRICE
    product = repository.get_product(
        context.chat_data.pop(EDITING, ""), only_available=False
    )
    if product is None:
        text, markup = _panel_view()
        await update.message.reply_text(
            f"محصول پیدا نشد.\n\n{text}", reply_markup=markup
        )
        return IDLE
    product.price = price
    repository.update_product(product)
    await update.message.reply_text(
        f"✅ قیمت به‌روزرسانی شد.\n\n{_product_text(product)}",
        reply_markup=keyboards.product(product),
    )
    return IDLE


# ---------- delete ----------


async def ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = await _product_from_query(update, keyboards.DELETE_PREFIX)
    if product is None:
        return IDLE
    if reason := _delete_blocker(context, product):
        await query.answer(reason, show_alert=True)
        return IDLE
    await query.answer()
    await query.edit_message_text(
        f"⚠️ آیا از حذف «{product.farsi_name}» مطمئن هستید؟\nاین کار قابل بازگشت نیست.",
        reply_markup=keyboards.confirm_delete(product),
    )
    return IDLE


async def delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = await _product_from_query(update, keyboards.DELETE_CONFIRM_PREFIX)
    if product is None:
        return IDLE
    # Checked again: an order may have used it since the confirmation was shown.
    if reason := _delete_blocker(context, product):
        await query.answer(reason, show_alert=True)
        return IDLE
    repository.delete_product(product.name)
    await query.answer("🗑 حذف شد.")
    text, markup = _category_view(
        product.category, note=f"🗑 «{product.farsi_name}» حذف شد."
    )
    await query.edit_message_text(text, reply_markup=markup)
    return IDLE


# ---------- create ----------


async def new_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _clear_input(context)
    context.chat_data[DRAFT] = {}
    await query.edit_message_text(
        "➕ محصول جدید (۱ از ۴)\n\n"
        "شناسه انگلیسی محصول را وارد کنید.\n"
        "فقط حروف کوچک انگلیسی، عدد و _ ؛ مثلاً pasta_simple",
        reply_markup=keyboards.cancel(keyboards.HOME),
    )
    return NEW_NAME


async def receive_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip().lower()
    if not NAME_PATTERN.fullmatch(value):
        await update.message.reply_text(
            "شناسه معتبر نیست. ۲ تا ۳۲ کاراکتر، با حرف انگلیسی شروع شود"
            " و فقط حروف کوچک انگلیسی، عدد و _ داشته باشد:",
            reply_markup=keyboards.cancel(keyboards.HOME),
        )
        return NEW_NAME
    if repository.name_taken(value):
        await update.message.reply_text(
            "این شناسه قبلاً استفاده شده است. شناسه دیگری وارد کنید:",
            reply_markup=keyboards.cancel(keyboards.HOME),
        )
        return NEW_NAME
    context.chat_data.setdefault(DRAFT, {})["name"] = value
    await update.message.reply_text(
        "➕ محصول جدید (۲ از ۴)\n\nنام فارسی محصول را وارد کنید:",
        reply_markup=keyboards.cancel(keyboards.HOME),
    )
    return NEW_FARSI_NAME


async def receive_new_farsi_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    value = update.message.text.strip()
    if not 2 <= len(value) <= 40:
        await update.message.reply_text(
            "نام باید بین ۲ تا ۴۰ کاراکتر باشد. دوباره وارد کنید:",
            reply_markup=keyboards.cancel(keyboards.HOME),
        )
        return NEW_FARSI_NAME
    if repository.name_taken(value):
        await update.message.reply_text(
            "محصولی با این نام وجود دارد. نام دیگری وارد کنید:",
            reply_markup=keyboards.cancel(keyboards.HOME),
        )
        return NEW_FARSI_NAME
    context.chat_data.setdefault(DRAFT, {})["farsi_name"] = value
    await update.message.reply_text(
        "➕ محصول جدید (۳ از ۴)\n\nقیمت را به تومان وارد کنید:",
        reply_markup=keyboards.cancel(keyboards.HOME),
    )
    return NEW_PRICE


async def receive_new_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price = _parse_price(update.message.text)
    if price is None:
        await update.message.reply_text(
            "قیمت معتبر نیست. فقط عدد به تومان وارد کنید (مثلاً ۲۰۰۰۰۰):",
            reply_markup=keyboards.cancel(keyboards.HOME),
        )
        return NEW_PRICE
    context.chat_data.setdefault(DRAFT, {})["price"] = price
    await update.message.reply_text(
        "➕ محصول جدید (۴ از ۴)\n\nدسته محصول را انتخاب کنید:",
        reply_markup=keyboards.new_category(),
    )
    return NEW_CATEGORY


def _draft_product(context: ContextTypes.DEFAULT_TYPE) -> Product | None:
    draft = context.chat_data.get(DRAFT) or {}
    if not {"name", "farsi_name", "price", "category"} <= draft.keys():
        return None
    return Product(**draft)


async def receive_new_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    category = ProductCategory.__members__.get(
        query.data.removeprefix(keyboards.NEW_CATEGORY_PREFIX)
    )
    if category is None:
        await query.answer("این دسته پیدا نشد.", show_alert=True)
        return NEW_CATEGORY
    context.chat_data.setdefault(DRAFT, {})["category"] = category
    product = _draft_product(context)
    if product is None:
        return await show_panel(update, context)
    await query.answer()
    await query.edit_message_text(
        f"📋 محصول جدید\n\n{_product_text(product)}\n\nثبت شود؟",
        reply_markup=keyboards.confirm_new(),
    )
    return NEW_CONFIRM


async def save_new_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = _draft_product(context)
    if product is None:
        return await show_panel(update, context)
    if repository.name_taken(product.name) or repository.name_taken(product.farsi_name):
        await query.answer("محصولی با این شناسه یا نام ثبت شده است.", show_alert=True)
        return NEW_CONFIRM
    repository.add_product(product)
    _clear_input(context)
    await query.answer("✅ محصول ثبت شد.")
    await query.edit_message_text(
        f"✅ محصول ثبت شد.\n\n{_product_text(product)}",
        reply_markup=keyboards.product(product),
    )
    return IDLE


# ---------- open orders ----------


def _local_time(moment: datetime) -> datetime:
    # created_at is saved in UTC; SQLite gives it back without a timezone.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone()


def order_text(order: Order) -> str:
    return "\n".join(
        [
            f"🧾 سفارش {fa_digits(order.order_number)} ({order.state.value})",
            f"🕐 {_local_time(order.created_at):%Y/%m/%d %H:%M}",
            "",
            *order_summary(order.customer, order.items, order.address),
        ]
    )


async def show_open_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Each confirmed order as its own message with finish/cancel buttons."""
    query = update.callback_query
    await query.answer()
    _clear_input(context)
    orders = repository.get_orders(OrderState.CONFIRMED)
    lines = [f"📋 سفارش‌های باز: {fa_digits(len(orders))}"]
    if not orders:
        lines.append("\nسفارش بازی وجود ندارد.")
    elif len(orders) > MAX_LISTED_ORDERS:
        lines.append(
            f"\n{fa_digits(MAX_LISTED_ORDERS)} سفارش قدیمی‌تر در پیام‌های زیر آمده است."
        )
    if waiting := len(pending_orders(context)):
        lines.append(f"\n⏳ {fa_digits(waiting)} سفارش هنوز در انتظار تأیید شماست.")
    await query.edit_message_text("\n".join(lines), reply_markup=keyboards.back_home())
    for order in orders[:MAX_LISTED_ORDERS]:
        await context.bot.send_message(
            update.effective_chat.id,
            order_text(order),
            reply_markup=keyboards.order_actions(order.order_number),
        )
    return IDLE


async def _open_order(update: Update, prefix: str) -> Order | None:
    """The confirmed order named in the callback data, or None after telling the admin.

    Answers the query only when returning None.
    """
    query = update.callback_query
    number = query.data.removeprefix(prefix)
    order = repository.get_order(int(number)) if number.isdigit() else None
    if order is None:
        await query.answer("سفارش پیدا نشد.", show_alert=True)
        await query.edit_message_reply_markup(None)
        return None
    if order.state != OrderState.CONFIRMED:
        await query.answer(
            f"این سفارش قبلاً «{order.state.value}» شده است.", show_alert=True
        )
        await query.edit_message_reply_markup(None)
        return None
    return order


async def _close_order(
    update: Update, context: ContextTypes.DEFAULT_TYPE, order: Order, state: OrderState
) -> None:
    """Save the new state, tell the customer, and mark the admin's message."""
    query = update.callback_query
    order = repository.update_order_state(order.order_number, state)
    number = fa_digits(order.order_number)
    if state == OrderState.FINISHED:
        await query.answer(f"🏁 سفارش {number} تمام شد.")
        status = "🏁 اتمام پخت"
        headline = (
            "🏁 سفارش شما آماده شد و به‌زودی ارسال می‌شود."
            if order.address
            else "🏁 سفارش شما آماده است؛ می‌توانید آن را تحویل بگیرید."
        )
    else:
        await query.answer(f"❌ سفارش {number} لغو شد.")
        status = "❌ لغو شد"
        headline = "❌ متأسفانه سفارش شما توسط ناشتایی لغو شد."
    try:
        await context.bot.send_message(
            order.customer.chat_id,
            "\n".join(
                [
                    headline,
                    "",
                    f"🔖 شماره سفارش: {number}",
                    "",
                    *order_summary(order.customer, order.items, order.address),
                ]
            ),
            reply_markup=customer_keyboards.new_order(),
        )
        notified = "مشتری مطلع شد."
    except TelegramError:
        log.exception("Could not notify customer %s", order.customer.chat_id)
        notified = "⚠️ ارسال پیام به مشتری ناموفق بود."
    # Keep what the message said (e.g. who ordered) and add the outcome below it.
    text = getattr(query.message, "text", None) or order_text(order)
    await query.edit_message_text(f"{text}\n\n{status} — {notified}")


async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if order := await _open_order(update, keyboards.ORDER_FINISH_PREFIX):
        await _close_order(update, context, order, OrderState.FINISHED)


async def ask_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if order := await _open_order(update, keyboards.ORDER_CANCEL_PREFIX):
        await update.callback_query.answer(
            f"برای لغو سفارش {fa_digits(order.order_number)} دوباره تأیید کنید."
        )
        await update.callback_query.edit_message_reply_markup(
            keyboards.confirm_cancel_order(order.order_number)
        )


async def show_order_actions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Back from the cancel confirmation."""
    if order := await _open_order(update, keyboards.ORDER_ACTIONS_PREFIX):
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(
            keyboards.order_actions(order.order_number)
        )


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if order := await _open_order(update, keyboards.ORDER_CANCEL_CONFIRM_PREFIX):
        await _close_order(update, context, order, OrderState.CANCELED)
