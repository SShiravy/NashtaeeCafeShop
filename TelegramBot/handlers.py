import logging
import secrets
from dataclasses import dataclass
from datetime import datetime

from telegram import (
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    ReplyParameters,
    Update,
    User,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from Database import repository
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import OrderState
from TelegramBot import keyboards as keyboards
from TelegramBot.PanelAdmin import keyboards as admin_keyboards
from TelegramBot.utils import (
    en_digits,
    fa_digits,
    format_minutes,
    format_price,
    normalize_phone,
)

log = logging.getLogger(__name__)

# Conversation states
MENU, CUSTOM_QTY, RECEIVE, NAME, PHONE, ADDRESS, CONFIRM = range(7)

MAX_QTY = 99


@dataclass(slots=True, frozen=True)
class PendingOrder:
    """A finished order waiting for the admin; saved to the DB only once confirmed."""

    items: list[Item]
    customer: Customer
    address: str | None
    admin_text: str
    customer_message_id: int  # the "waiting for confirmation" message


CHOOSE_CATEGORY = "لطفاً دسته موردنظر را انتخاب کنید:"
ASK_NAME = "لطفاً نام و نام خانوادگی خود را وارد کنید:"
ASK_PHONE = "شماره تماس را وارد کنید یا از دکمه زیر استفاده کنید:"
ASK_RECEIVE = "📦 روش دریافت سفارش را انتخاب کنید:"
CANCELLED = "❌ سفارش لغو شد."


# ---------- cart helpers ----------


def _cart(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Item]:
    """Product.name -> Item"""
    return context.user_data.setdefault("cart", {})


def _items_total(items: list[Item]) -> int:
    return sum(item.product.price * item.count for item in items)


def _item_lines(items: list[Item]) -> list[str]:
    return [
        f"{fa_digits(n)}. {item.product.farsi_name} × {fa_digits(item.count)}"
        f" — {format_price(item.product.price * item.count)} تومان"
        for n, item in enumerate(items, 1)
    ]


def _cart_text(cart: dict[str, Item]) -> str:
    if not cart:
        return "🛒 سبد خرید شما خالی است."
    items = list(cart.values())
    return "\n".join(
        [
            "🛒 سبد خرید شما:",
            "",
            *_item_lines(items),
            "",
            "────────────",
            f"💰 جمع کل: {format_price(_items_total(items))} تومان",
        ]
    )


def _add_to_cart(context: ContextTypes.DEFAULT_TYPE, product: Product, qty: int) -> str:
    cart = _cart(context)
    previous = cart[product.name].count if product.name in cart else 0
    # A new Item, so its prep time is recalculated for the new count.
    item = cart[product.name] = Item(product, min(previous + qty, MAX_QTY))
    lines = [
        f"✅ {product.farsi_name} × {fa_digits(qty)} به سبد خرید اضافه شد.",
        "",
        f"🛒 تعداد این مورد در سبد: {fa_digits(item.count)}",
        f"💰 جمع سبد خرید: {format_price(_items_total(list(cart.values())))} تومان",
    ]
    if item.count == MAX_QTY:
        lines.append(f"(حداکثر تعداد هر مورد {fa_digits(MAX_QTY)} عدد است.)")
    return "\n".join(lines)


def _customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Customer:
    return Customer(
        name=context.user_data["name"],
        phone=context.user_data["phone"],
        chat_id=str(update.effective_chat.id),
    )


def _address(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """None means pickup at the cafe."""
    if context.user_data["delivery"] == keyboards.DELIVERY:
        return context.user_data["address"]
    return None


def order_summary(
    customer: Customer, items: list[Item], address: str | None
) -> list[str]:
    lines = [
        f"👤 نام: {customer.name}",
        f"📞 تماس: {customer.phone}",
        f"📦 دریافت: {'ارسال' if address else 'حضوری'}",
    ]
    if address:
        lines.append(f"📍 آدرس: {address}")
    lines += [
        "",
        "🍽 اقلام:",
        *_item_lines(items),
        "",
        f"💰 جمع کل: {format_price(_items_total(items))} تومان",
    ]
    return lines


def _open_orders_minutes() -> int:
    """Prep time of every open (confirmed) order; the kitchen works through them all."""
    return sum(
        item.total_minutes
        for order in repository.get_orders(OrderState.CONFIRMED)
        for item in order.items
    )


def _estimate_lines(minutes: int, address: str | None) -> list[str]:
    note = "زمان ارسال را شامل نمی‌شود." if address else "تخمینی است."
    return [
        f"⏱ زمان تقریبی آماده شدن سفارش: حدود {format_minutes(minutes)}",
        f"(با احتساب سفارش‌های در صف؛ {note})",
    ]


def _main_menu() -> InlineKeyboardMarkup:
    return keyboards.main_menu(repository.get_categories())


# ---------- /start and menu navigation ----------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    name = update.effective_user.first_name or "دوست ناشتایی"
    # Also removes a contact keyboard left over from an unfinished order.
    await update.message.reply_text(
        f"سلام {name} 🌿\nبه ناشتایی خوش آمدید.", reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(CHOOSE_CATEGORY, reply_markup=_main_menu())
    return MENU


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(CHOOSE_CATEGORY, reply_markup=_main_menu())
    return MENU


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    category = ProductCategory.__members__.get(
        query.data.removeprefix(keyboards.CATEGORY_PREFIX)
    )
    products = [p for p in repository.get_products() if p.category == category]
    if not products:
        await query.answer("این دسته پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        f"{category.value}\n\nیک مورد را انتخاب کنید:",
        reply_markup=keyboards.category_items(products),
    )
    return MENU


async def show_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    product = repository.get_product(query.data.removeprefix(keyboards.ITEM_PREFIX))
    if product is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        f"🍽 {product.farsi_name}\n\nقیمت واحد: {format_price(product.price)} تومان"
        "\n\nتعداد را انتخاب کنید:",
        reply_markup=keyboards.quantity(product),
    )
    return MENU


async def choose_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    name, _, qty = query.data.removeprefix(keyboards.QTY_PREFIX).rpartition(":")
    product = repository.get_product(name)
    if product is None or not qty.isdigit():
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        _add_to_cart(context, product, int(qty)), reply_markup=keyboards.after_add()
    )
    return MENU


async def ask_custom_quantity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    product = repository.get_product(
        query.data.removeprefix(keyboards.CUSTOM_QTY_PREFIX)
    )
    if product is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    context.user_data["pending_product"] = product
    await query.answer()
    await query.edit_message_text(
        f"🍽 {product.farsi_name}\n\nتعداد را وارد کنید (۱ تا {fa_digits(MAX_QTY)}):",
        reply_markup=keyboards.custom_quantity(product),
    )
    return CUSTOM_QTY


async def receive_custom_quantity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    product = context.user_data.get("pending_product")
    if product is None:
        await update.message.reply_text(CHOOSE_CATEGORY, reply_markup=_main_menu())
        return MENU
    try:
        qty = int(en_digits(update.message.text.strip()))
    except ValueError:
        await update.message.reply_text("لطفاً فقط عدد وارد کنید.")
        return CUSTOM_QTY
    if not 1 <= qty <= MAX_QTY:
        await update.message.reply_text(
            f"تعداد باید بین ۱ تا {fa_digits(MAX_QTY)} باشد."
        )
        return CUSTOM_QTY
    del context.user_data["pending_product"]
    await update.message.reply_text(
        _add_to_cart(context, product, qty), reply_markup=keyboards.after_add()
    )
    return MENU


# ---------- cart ----------


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cart = _cart(context)
    await query.edit_message_text(
        _cart_text(cart), reply_markup=keyboards.cart(bool(cart))
    )
    return MENU


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data["cart"] = {}
    await query.answer("سبد خرید خالی شد.")
    await query.edit_message_text(
        f"🛒 سبد خرید خالی شد.\n\n{CHOOSE_CATEGORY}", reply_markup=_main_menu()
    )
    return MENU


async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not _cart(context):
        await query.answer("سبد خرید خالی است.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(ASK_RECEIVE, reply_markup=keyboards.receive_method())
    return RECEIVE


# ---------- customer details ----------


async def choose_receive_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    method = query.data.removeprefix(keyboards.RECEIVE_PREFIX)
    if method not in (keyboards.PICKUP, keyboards.DELIVERY):
        await query.answer()
        return RECEIVE
    context.user_data["delivery"] = method
    await query.answer()
    title = "🚚 ارسال" if method == keyboards.DELIVERY else "🏪 دریافت حضوری"
    await query.edit_message_text(f"{title}\n\n{ASK_NAME}")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if not 2 <= len(value) <= 64:
        await update.message.reply_text("لطفاً نام معتبر وارد کنید.")
        return NAME
    context.user_data["name"] = value
    await update.message.reply_text(ASK_PHONE, reply_markup=keyboards.contact_request())
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    phone = normalize_phone(
        message.contact.phone_number if message.contact else message.text
    )
    if phone is None:
        await message.reply_text(
            "شماره تماس معتبر نیست. دوباره وارد کنید:",
            reply_markup=keyboards.contact_request(),
        )
        return PHONE
    context.user_data["phone"] = phone
    if context.user_data["delivery"] == keyboards.DELIVERY:
        await message.reply_text(
            "آدرس کامل محل تحویل را وارد کنید:", reply_markup=ReplyKeyboardRemove()
        )
        return ADDRESS
    # An inline keyboard and ReplyKeyboardRemove can't share one message.
    await message.reply_text(
        "✅ شماره تماس ثبت شد.", reply_markup=ReplyKeyboardRemove()
    )
    return await _show_summary(update, context)


async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if not 10 <= len(value) <= 300:
        await update.message.reply_text("لطفاً آدرس کامل‌تری وارد کنید.")
        return ADDRESS
    context.user_data["address"] = value
    return await _show_summary(update, context)


async def _show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    items = list(_cart(context).values())
    address = _address(context)
    # Not confirmed yet, so it's added on top of the open orders.
    minutes = _open_orders_minutes() + sum(item.total_minutes for item in items)
    summary = order_summary(_customer(update, context), items, address)
    text = "\n".join(
        ["📋 خلاصه سفارش", "", *summary, "", *_estimate_lines(minutes, address)]
    )
    await update.effective_message.reply_text(text, reply_markup=keyboards.confirm())
    return CONFIRM


# ---------- confirmation ----------


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Customer finished the order: send it to the admin for approval."""
    query = update.callback_query
    customer = _customer(update, context)
    items = list(_cart(context).values())
    address = _address(context)
    summary = order_summary(customer, items, address)
    pending_id = secrets.token_hex(4)
    admin_text = "\n".join(
        [
            "🆕 سفارش جدید ناشتایی (در انتظار تأیید)",
            "",
            f"🕐 {datetime.now():%Y/%m/%d %H:%M}",
            f"🆔 تلگرام: {_telegram_user(update.effective_user)}",
            "",
            *summary,
        ]
    )
    try:
        await context.bot.send_message(
            context.bot_data["admin_id"],
            admin_text,
            reply_markup=keyboards.admin_decision(pending_id),
        )
    except TelegramError:
        log.exception(
            "Could not send an order of chat %s to the admin", customer.chat_id
        )
        await query.answer(
            "ارسال سفارش انجام نشد. لطفاً چند لحظه بعد دوباره تلاش کنید.",
            show_alert=True,
        )
        return CONFIRM
    await query.answer()
    # Kept as the customer's copy; "new order" continues in a new message.
    message = await query.edit_message_text(
        "\n".join(
            [
                "⏳ سفارش شما برای ناشتایی ارسال شد و در انتظار تأیید است.",
                "پس از تأیید، پیام تأیید سفارش برای شما ارسال می‌شود.",
                "",
                *summary,
            ]
        ),
        reply_markup=keyboards.new_order(),
    )
    pending_orders(context)[pending_id] = PendingOrder(
        items, customer, address, admin_text, message.message_id
    )
    context.user_data.clear()
    return ConversationHandler.END


def _telegram_user(user: User) -> str:
    username = f" @{user.username}" if user.username else ""
    return f"{user.full_name}{username} ({user.id})"


async def edit_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(ASK_RECEIVE, reply_markup=keyboards.receive_method())
    return RECEIVE


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(CANCELLED, reply_markup=keyboards.new_order())
    return ConversationHandler.END


async def start_new_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    # Sent as a new message so the confirmed (or cancelled) order stays visible.
    await context.bot.send_message(
        update.effective_chat.id, CHOOSE_CATEGORY, reply_markup=_main_menu()
    )
    return MENU


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        f"{CANCELLED}\n\nبرای سفارش جدید /start را بزنید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------- admin decisions ----------


def pending_orders(context: ContextTypes.DEFAULT_TYPE) -> dict[str, PendingOrder]:
    # In memory: orders still waiting for the admin are lost if the bot restarts.
    return context.bot_data.setdefault("pending_orders", {})


async def _take_pending(
    update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str
) -> tuple[str, PendingOrder] | None:
    """Pop the pending order of an admin button, or answer why it can't be handled."""
    query = update.callback_query
    if str(update.effective_chat.id) != str(context.bot_data["admin_id"]):
        await query.answer("⛔ دسترسی ندارید.", show_alert=True)
        return None
    pending_id = query.data.removeprefix(prefix)
    pending = pending_orders(context).pop(pending_id, None)
    if pending is None:
        await query.answer(
            "این سفارش قبلاً بررسی شده یا دیگر در دسترس نیست.", show_alert=True
        )
        await query.edit_message_reply_markup(None)
        return None
    return pending_id, pending


async def _notify_customer(
    context: ContextTypes.DEFAULT_TYPE, pending: PendingOrder, text: str
) -> None:
    try:
        await context.bot.send_message(
            pending.customer.chat_id,
            text,
            reply_parameters=ReplyParameters(
                pending.customer_message_id, allow_sending_without_reply=True
            ),
            reply_markup=keyboards.new_order(),
        )
    except TelegramError:
        log.exception("Could not notify customer %s", pending.customer.chat_id)


async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    taken = await _take_pending(update, context, keyboards.ADMIN_CONFIRM_PREFIX)
    if taken is None:
        return
    pending_id, pending = taken
    try:
        order = repository.create_order(
            pending.items, pending.customer, pending.address, OrderState.CONFIRMED
        )
    except Exception:
        log.exception("Could not save the order of chat %s", pending.customer.chat_id)
        pending_orders(context)[pending_id] = pending  # let the admin retry
        await query.answer(
            "ثبت سفارش در دیتابیس انجام نشد. لطفاً دوباره تلاش کنید.", show_alert=True
        )
        return
    number = fa_digits(order.order_number)
    await query.answer(f"سفارش {number} تأیید شد.")
    log.info("Order %s confirmed:\n%s", order.order_number, pending.admin_text)
    # From here on the order is open: the admin finishes or cancels it.
    await query.edit_message_text(
        f"{pending.admin_text}\n\n✅ تأیید شد — شماره سفارش: {number}",
        reply_markup=admin_keyboards.order_actions(order.order_number),
    )
    summary = order_summary(order.customer, order.items, order.address)
    await _notify_customer(
        context,
        pending,
        "\n".join(
            [
                "✅ سفارش شما توسط ناشتایی تأیید شد.",
                "",
                f"🔖 شماره سفارش: {number}",
                # Now confirmed, so the open orders already include this one.
                *_estimate_lines(_open_orders_minutes(), order.address),
                "",
                *summary,
            ]
        ),
    )


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    taken = await _take_pending(update, context, keyboards.ADMIN_CANCEL_PREFIX)
    if taken is None:
        return
    _, pending = taken
    await query.answer("سفارش رد شد.")
    await query.edit_message_text(f"{pending.admin_text}\n\n❌ رد شد")
    summary = order_summary(pending.customer, pending.items, pending.address)
    await _notify_customer(
        context,
        pending,
        "\n".join(
            [
                "❌ متأسفانه سفارش زیر توسط ناشتایی تأیید نشد.",
                "",
                *summary,
            ]
        ),
    )


# ---------- outside the conversation ----------


async def expired_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer(
        "این دکمه دیگر فعال نیست. برای شروع دوباره /start را بزنید.", show_alert=True
    )


async def use_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "لطفاً از دکمه‌ها استفاده کنید یا برای شروع /start را بزنید."
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Pressing a button that would re-render the same message is harmless.
    if (
        isinstance(context.error, BadRequest)
        and "not modified" in context.error.message
    ):
        return
    log.error("Error while handling update %s", update, exc_info=context.error)
