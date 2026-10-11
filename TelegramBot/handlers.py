import logging
import random
import string

from telegram import ReplyKeyboardRemove, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from TelegramBot import keyboards as keyboards
from TelegramBot.menu import CATEGORIES, ITEMS, MAX_QTY, MenuItem
from TelegramBot.utils import en_digits, fa_digits, format_price, normalize_phone

log = logging.getLogger(__name__)

# Conversation states
MENU, CUSTOM_QTY, RECEIVE, NAME, COMPANY, PHONE, ADDRESS, CONFIRM = range(8)

CHOOSE_CATEGORY = "لطفاً دسته موردنظر را انتخاب کنید:"
ASK_NAME = "لطفاً نام و نام خانوادگی خود را وارد کنید:"
ASK_PHONE = "شماره تماس را وارد کنید یا از دکمه زیر استفاده کنید:"
ASK_RECEIVE = "📦 روش دریافت سفارش را انتخاب کنید:"
CANCELLED = "❌ سفارش لغو شد."


# ---------- cart helpers ----------


def _cart(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """item id -> quantity"""
    return context.user_data.setdefault("cart", {})


def _cart_total(cart: dict[str, int]) -> int:
    return sum(ITEMS[item_id].price * qty for item_id, qty in cart.items())


def _cart_lines(cart: dict[str, int]) -> list[str]:
    return [
        f"{fa_digits(n)}. {ITEMS[item_id].name} × {fa_digits(qty)}"
        f" — {format_price(ITEMS[item_id].price * qty)} تومان"
        for n, (item_id, qty) in enumerate(cart.items(), 1)
    ]


def _cart_text(cart: dict[str, int]) -> str:
    if not cart:
        return "🛒 سبد خرید شما خالی است."
    return "\n".join(
        [
            "🛒 سبد خرید شما:",
            "",
            *_cart_lines(cart),
            "",
            "────────────",
            f"💰 جمع کل: {format_price(_cart_total(cart))} تومان",
        ]
    )


def _add_to_cart(context: ContextTypes.DEFAULT_TYPE, item: MenuItem, qty: int) -> str:
    cart = _cart(context)
    cart[item.id] = min(cart.get(item.id, 0) + qty, MAX_QTY)
    lines = [
        f"✅ {item.name} × {fa_digits(qty)} به سبد خرید اضافه شد.",
        "",
        f"🛒 تعداد این مورد در سبد: {fa_digits(cart[item.id])}",
        f"💰 جمع سبد خرید: {format_price(_cart_total(cart))} تومان",
    ]
    if cart[item.id] == MAX_QTY:
        lines.append(f"(حداکثر تعداد هر مورد {fa_digits(MAX_QTY)} عدد است.)")
    return "\n".join(lines)


def _order_summary(data: dict) -> list[str]:
    is_delivery = data["delivery"] == keyboards.DELIVERY
    lines = [
        f"👤 نام: {data['name']}",
        f"📞 تماس: {data['phone']}",
        f"📦 دریافت: {'ارسال' if is_delivery else 'حضوری'}",
    ]
    if is_delivery:
        lines += [f"🏢 شرکت: {data['company']}", f"📍 آدرس: {data['address']}"]
    cart = data["cart"]
    lines += [
        "",
        "🍽 اقلام:",
        *_cart_lines(cart),
        "",
        f"💰 جمع کل: {format_price(_cart_total(cart))} تومان",
    ]
    return lines


# ---------- /start and menu navigation ----------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    name = update.effective_user.first_name or "دوست ناشتایی"
    # Also removes a contact keyboard left over from an unfinished order.
    await update.message.reply_text(
        f"سلام {name} 🌿\nبه ناشتایی خوش آمدید.", reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(CHOOSE_CATEGORY, reply_markup=keyboards.main_menu())
    return MENU


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(CHOOSE_CATEGORY, reply_markup=keyboards.main_menu())
    return MENU


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    category = CATEGORIES.get(query.data.removeprefix(keyboards.CATEGORY_PREFIX))
    if category is None:
        await query.answer("این دسته پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        f"{category.title}\n\nیک مورد را انتخاب کنید:",
        reply_markup=keyboards.category_items(category.id),
    )
    return MENU


async def show_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    item = ITEMS.get(query.data.removeprefix(keyboards.ITEM_PREFIX))
    if item is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        f"🍽 {item.name}\n\nقیمت واحد: {format_price(item.price)} تومان\n\nتعداد را انتخاب کنید:",
        reply_markup=keyboards.quantity(item.id),
    )
    return MENU


async def choose_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    item_id, _, qty = query.data.removeprefix(keyboards.QTY_PREFIX).rpartition(":")
    item = ITEMS.get(item_id)
    if item is None or not qty.isdigit():
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    await query.answer()
    await query.edit_message_text(
        _add_to_cart(context, item, int(qty)), reply_markup=keyboards.after_add()
    )
    return MENU


async def ask_custom_quantity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    item = ITEMS.get(query.data.removeprefix(keyboards.CUSTOM_QTY_PREFIX))
    if item is None:
        await query.answer("محصول پیدا نشد.", show_alert=True)
        return MENU
    context.user_data["pending_item"] = item.id
    await query.answer()
    await query.edit_message_text(
        f"🍽 {item.name}\n\nتعداد را وارد کنید (۱ تا {fa_digits(MAX_QTY)}):",
        reply_markup=keyboards.custom_quantity(item.id),
    )
    return CUSTOM_QTY


async def receive_custom_quantity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    item = ITEMS.get(context.user_data.get("pending_item", ""))
    if item is None:
        await update.message.reply_text(
            CHOOSE_CATEGORY, reply_markup=keyboards.main_menu()
        )
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
    del context.user_data["pending_item"]
    await update.message.reply_text(
        _add_to_cart(context, item, qty), reply_markup=keyboards.after_add()
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
        f"🛒 سبد خرید خالی شد.\n\n{CHOOSE_CATEGORY}", reply_markup=keyboards.main_menu()
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
    if context.user_data["delivery"] == keyboards.DELIVERY:
        await update.message.reply_text("نام شرکت، سازمان یا مجموعه را وارد کنید:")
        return COMPANY
    await update.message.reply_text(ASK_PHONE, reply_markup=keyboards.contact_request())
    return PHONE


async def get_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if not 2 <= len(value) <= 100:
        await update.message.reply_text("لطفاً نام شرکت یا مجموعه را وارد کنید.")
        return COMPANY
    context.user_data["company"] = value
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
    text = "\n".join(["📋 خلاصه سفارش", "", *_order_summary(context.user_data)])
    await update.effective_message.reply_text(text, reply_markup=keyboards.confirm())
    return CONFIRM


# ---------- confirmation ----------


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    order_id = "NAS-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=5)
    )
    total = _cart_total(context.user_data["cart"])
    log.info(
        "New order %s from user %s:\n%s",
        order_id,
        update.effective_user.id,
        "\n".join(_order_summary(context.user_data)),
    )
    await query.edit_message_text(
        f"✅ سفارش شما با موفقیت ثبت شد.\n\n"
        f"🔖 شماره سفارش: {order_id}\n"
        f"💰 مبلغ: {format_price(total)} تومان",
        reply_markup=keyboards.new_order(),
    )
    context.user_data.clear()
    return ConversationHandler.END


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


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        f"{CANCELLED}\n\nبرای سفارش جدید /start را بزنید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


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
