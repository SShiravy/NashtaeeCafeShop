"""Admin panel for the TELEGRAM_ADMIN_ID chat: product CRUD and open orders.

Wired up in TelegramBot.bot.
"""

import logging
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from Database import repository
from Database.backup import backup_to, database_file
from Models.menu import Product, ProductCategory
from Models.order import Order, OrderState
from TelegramBot import keyboards as customer_keyboards
from TelegramBot.handlers import order_summary, pending_orders
from TelegramBot.PanelAdmin import keyboards
from TelegramBot.utils import en_digits, fa_digits, format_price

log = logging.getLogger(__name__)

# Conversation states
IDLE, EDIT_FIELD, NEW_NAME, NEW_FARSI_NAME, NEW_NUMBER, NEW_CATEGORY, NEW_CONFIRM = (
    range(7)
)

MAX_LISTED_ORDERS = 20  # one message each; more would hit Telegram's rate limits
NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,31}")
NEW_STEPS = 6  # name, Farsi name, the three FIELDS, category

# chat_data keys; chat_data, because the customer side clears user_data on /start.
DRAFT = "admin_new_product"  # dict of Product fields while creating a product
EDITING = "admin_editing"  # (Product.name, field) being edited


@dataclass(frozen=True, slots=True)
class _Field:
    """A number field of Product that the admin types in."""

    title: str
    prompt: str  # {name} is the product's Farsi name
    error: str
    maximum: int
    show: Callable[[int], str]


# Asked in this order when creating a product; each is editable afterwards.
FIELDS = {
    "price": _Field(
        "قیمت",
        "💰 قیمت «{name}» را به تومان وارد کنید:",
        "قیمت معتبر نیست. فقط عدد به تومان وارد کنید (مثلاً ۲۰۰۰۰۰):",
        1_000_000_000,
        lambda value: f"{format_price(value)} تومان",
    ),
    "prep_count": _Field(
        "تعداد هر نوبت پخت",
        "🔢 چند عدد «{name}» با هم در یک نوبت آماده می‌شود؟ (۱ تا ۹۹)",
        "عدد معتبر نیست. عددی بین ۱ تا ۹۹ وارد کنید:",
        99,
        lambda value: f"{fa_digits(value)} عدد",
    ),
    "prep_minutes": _Field(
        "زمان هر نوبت پخت",
        "⏱ هر نوبت آماده‌سازی «{name}» چند دقیقه طول می‌کشد؟ (۱ تا ۶۰۰)",
        "عدد معتبر نیست. عددی بین ۱ تا ۶۰۰ دقیقه وارد کنید:",
        600,
        lambda value: f"{fa_digits(value)} دقیقه",
    ),
}


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
            (
                f"⏱ هر نوبت پخت: تا {fa_digits(product.prep_count)} عدد"
                f" در {fa_digits(product.prep_minutes)} دقیقه"
            ),
            f"📌 وضعیت: {'🟢 موجود' if product.available else '🔴 ناموجود'}",
        ]
    )


def _parse_number(text: str, maximum: int) -> int | None:
    """'۲۰۰٬۰۰۰' or '200,000' -> 200000; None unless it's between 1 and maximum."""
    digits = re.sub(r"[\s,٬،]", "", en_digits(text))
    if not digits.isdigit():
        return None
    number = int(digits)
    return number if 1 <= number <= maximum else None


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


async def ask_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    field, _, name = query.data.removeprefix(keyboards.EDIT_PREFIX).partition(":")
    product = repository.get_product(name, only_available=False)
    if field not in FIELDS or product is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return IDLE
    spec = FIELDS[field]
    context.chat_data[EDITING] = (product.name, field)
    await query.answer()
    await query.edit_message_text(
        f"{spec.prompt.format(name=product.farsi_name)}"
        f"\n(مقدار فعلی: {spec.show(getattr(product, field))})",
        reply_markup=keyboards.cancel(keyboards.PRODUCT_PREFIX + product.name),
    )
    return EDIT_FIELD


async def receive_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name, field = context.chat_data.get(EDITING, ("", "price"))
    spec = FIELDS[field]
    value = _parse_number(update.message.text, spec.maximum)
    if value is None:
        await update.message.reply_text(spec.error)
        return EDIT_FIELD
    context.chat_data.pop(EDITING, None)
    product = repository.get_product(name, only_available=False)
    if product is None:
        text, markup = _panel_view()
        await update.message.reply_text(
            f"محصول پیدا نشد.\n\n{text}", reply_markup=markup
        )
        return IDLE
    setattr(product, field, value)
    repository.update_product(product)
    await update.message.reply_text(
        f"✅ {spec.title} به‌روزرسانی شد.\n\n{_product_text(product)}",
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
        f"➕ محصول جدید (۱ از {fa_digits(NEW_STEPS)})\n\n"
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
        f"➕ محصول جدید (۲ از {fa_digits(NEW_STEPS)})\n\nنام فارسی محصول را وارد کنید:",
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
        _new_number_prompt(context), reply_markup=keyboards.cancel(keyboards.HOME)
    )
    return NEW_NUMBER


def _next_number_field(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    draft = context.chat_data.setdefault(DRAFT, {})
    return next((field for field in FIELDS if field not in draft), None)


def _new_number_prompt(context: ContextTypes.DEFAULT_TYPE) -> str:
    field = _next_number_field(context)
    step = 3 + list(FIELDS).index(field)
    name = context.chat_data[DRAFT].get("farsi_name", "")
    return (
        f"➕ محصول جدید ({fa_digits(step)} از {fa_digits(NEW_STEPS)})\n\n"
        f"{FIELDS[field].prompt.format(name=name)}"
    )


async def receive_new_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Price, then batch size, then batch time (the FIELDS, in order)."""
    field = _next_number_field(context)
    if field is None:  # all typed already; only the category is left
        await update.message.reply_text(
            "دسته محصول را انتخاب کنید:", reply_markup=keyboards.new_category()
        )
        return NEW_CATEGORY
    value = _parse_number(update.message.text, FIELDS[field].maximum)
    if value is None:
        await update.message.reply_text(
            FIELDS[field].error, reply_markup=keyboards.cancel(keyboards.HOME)
        )
        return NEW_NUMBER
    context.chat_data[DRAFT][field] = value
    if _next_number_field(context) is not None:
        await update.message.reply_text(
            _new_number_prompt(context), reply_markup=keyboards.cancel(keyboards.HOME)
        )
        return NEW_NUMBER
    await update.message.reply_text(
        f"➕ محصول جدید ({fa_digits(NEW_STEPS)} از {fa_digits(NEW_STEPS)})"
        "\n\nدسته محصول را انتخاب کنید:",
        reply_markup=keyboards.new_category(),
    )
    return NEW_CATEGORY


def _draft_product(context: ContextTypes.DEFAULT_TYPE) -> Product | None:
    draft = context.chat_data.get(DRAFT) or {}
    if not {"name", "farsi_name", "category", *FIELDS} <= draft.keys():
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
            *order_summary(order.customer, order.items, order.address, order.discount),
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
                    *order_summary(
                        order.customer, order.items, order.address, order.discount
                    ),
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


# ---------- database backup ----------


async def send_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a copy of the database to the admin chat (daily job and /backup)."""
    admin_id = context.bot_data["admin_id"]
    if database_file() is None:
        log.warning("Skipping the backup: only SQLite databases can be backed up")
        return
    now = datetime.now()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"Nashtaee-{now:%Y-%m-%d_%H-%M}.db"
        try:
            backup_to(path)
            with path.open("rb") as file:
                await context.bot.send_document(
                    admin_id,
                    file,
                    filename=path.name,
                    caption=f"🗄 بک اپ دیتابیس ناشتایی\n🕐 {now:%Y/%m/%d %H:%M}",
                )
        except Exception:
            log.exception("Could not send the database backup to the admin")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/backup: a backup right now, on top of the daily one."""
    await send_backup(context)
