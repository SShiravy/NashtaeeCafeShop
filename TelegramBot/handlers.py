import logging
import secrets
from dataclasses import dataclass, replace
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
from Models.order import NO_DISCOUNT, Discount, OrderState
from Models.poll import POLL, PollAnswer, PollQuestion, PollResponse
from Models.referral import JoinResult, ReferralPlan
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
MENU, CUSTOM_QTY, RECEIVE, NAME, PHONE, ADDRESS, CONFIRM, COMPANY, POLL_TEXT = range(9)

MAX_QTY = 99

# user_data key: where to go after the customer types a new name, company or
# phone: "summary", "profile" or "checkout" (carry on to the address/summary).
# Unset while a first-time customer is entering them.
INFO_RETURN = "info_return"
INFO_LABELS = {"name": "نام", "company": "نام شرکت", "phone": "شماره تماس"}


@dataclass(slots=True, frozen=True)
class PendingOrder:
    """A finished order waiting for the admin; saved to the DB only once confirmed."""

    items: list[Item]
    customer: Customer
    address: str | None
    admin_text: str
    customer_message_id: int  # the "waiting for confirmation" message
    discount: Discount


CHOOSE_CATEGORY = "لطفاً دسته موردنظر را انتخاب کنید:"
ASK_NAME = "لطفاً نام و نام خانوادگی خود را وارد کنید:"
ASK_COMPANY = "🏢 نام شرکت خود را وارد کنید:"
ASK_PHONE = "شماره تماس را وارد کنید یا از دکمه زیر استفاده کنید:"
ASK_RECEIVE = "📦 روش دریافت سفارش را انتخاب کنید:"
ASK_ADDRESS = "📍 آدرس کامل محل تحویل را وارد کنید:"
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
        chat_id=_chat_id(update),
        company=context.user_data["company"],
    )


def _chat_id(update: Update) -> str:
    return str(update.effective_chat.id)


async def _send(
    update: Update, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Edit the message whose button was pressed, or reply to a typed message."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


def _address(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """None means pickup at the cafe."""
    if context.user_data["delivery"] == keyboards.DELIVERY:
        return context.user_data["address"]
    return None


def order_summary(
    customer: Customer,
    items: list[Item],
    address: str | None,
    discount: Discount = NO_DISCOUNT,
) -> list[str]:
    lines = [f"👤 نام: {customer.name}"]
    if customer.company:
        lines.append(f"🏢 شرکت: {customer.company}")
    lines += [
        f"📞 تماس: {customer.phone}",
        f"📦 دریافت: {'ارسال' if address else 'حضوری'}",
    ]
    if address:
        lines.append(f"📍 آدرس: {address}")
    total = _items_total(items)
    lines += [
        "",
        "🍽 اقلام:",
        *_item_lines(items),
        "",
        f"💰 جمع کل: {format_price(total)} تومان",
    ]
    if discount.first_buy:
        lines.append(
            f"🎁 تخفیف اولین خرید (لینک دعوت): {format_price(discount.first_buy)} تومان"
        )
    if discount.reward:
        lines.append(f"🎁 تخفیف دعوت از دوستان: {format_price(discount.reward)} تومان")
    if discount.total:
        lines.append(
            f"💳 مبلغ قابل پرداخت: {format_price(total - discount.total)} تومان"
        )
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


def _plan(context: ContextTypes.DEFAULT_TYPE) -> ReferralPlan:
    return context.bot_data["referral_plan"]


def _order_discount(
    context: ContextTypes.DEFAULT_TYPE, chat_id: str, items: list[Item]
) -> Discount:
    """Referral discounts of a new order, leaving out the ones already used by the
    chat's orders still waiting for the admin (they aren't in the database yet)."""
    plan = _plan(context)
    waiting = [
        pending.discount
        for pending in pending_orders(context).values()
        if pending.customer.chat_id == chat_id
    ]
    first_buy = not any(d.first_buy for d in waiting) and (
        repository.first_buy_discount_due(chat_id)
    )
    reward_left = plan.reward_left(repository.get_referral_stats(chat_id)) - sum(
        d.reward for d in waiting
    )
    return plan.discount(_items_total(items), first_buy, reward_left)


# ---------- /start and menu navigation ----------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    chat_id = _chat_id(update)
    customer = repository.get_customer(chat_id)
    name = customer.name if customer else update.effective_user.first_name
    text = f"سلام {name or 'دوست ناشتایی'} 🌿\nبه ناشتایی خوش آمدید."
    payload = context.args[0] if context.args else ""
    # Opened with t.me/<bot>?start=ref_<invite code>
    if payload.startswith(keyboards.REFERRAL_START_PREFIX):
        code = payload.removeprefix(keyboards.REFERRAL_START_PREFIX)
        if note := _join_with_code(context, chat_id, code):
            text += f"\n\n{note}"
    # Also removes a contact keyboard left over from an unfinished order.
    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    if context.args == [keyboards.POLL]:  # opened with t.me/<bot>?start=poll
        return await open_poll(update, context)
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
    customer = repository.get_customer(_chat_id(update))
    if customer is None:
        # First time: ask name, company and phone once; they're remembered.
        context.user_data.pop(INFO_RETURN, None)
        title = "🚚 ارسال" if method == keyboards.DELIVERY else "🏪 دریافت حضوری"
        await query.edit_message_text(f"{title}\n\n{ASK_NAME}")
        return NAME
    _remember(context, customer)
    if not customer.company:
        # Saved before the company was asked for: ask just that, then carry on.
        context.user_data[INFO_RETURN] = "checkout"
        await query.edit_message_text(ASK_COMPANY)
        return COMPANY
    return await _continue_checkout(update, context)


def _remember(context: ContextTypes.DEFAULT_TYPE, customer: Customer) -> None:
    context.user_data.update(
        name=customer.name, company=customer.company, phone=customer.phone
    )


async def _continue_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """With the customer's details known: the address for delivery, else the summary."""
    if context.user_data["delivery"] == keyboards.DELIVERY:
        return await _ask_address(update, context)
    return await _show_summary(update, context)


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if not 2 <= len(value) <= 64:
        await update.message.reply_text("لطفاً نام معتبر وارد کنید.")
        return NAME
    if context.user_data.get(INFO_RETURN):
        return await _update_info(update, context, name=value)
    context.user_data["name"] = value
    await update.message.reply_text(ASK_COMPANY)
    return COMPANY


async def get_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if not 2 <= len(value) <= 100:
        await update.message.reply_text("لطفاً نام شرکت را وارد کنید (۲ تا ۱۰۰ حرف).")
        return COMPANY
    if context.user_data.get(INFO_RETURN):
        return await _update_info(update, context, company=value)
    context.user_data["company"] = value
    await update.message.reply_text(ASK_PHONE, reply_markup=keyboards.contact_request())
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    editing = bool(context.user_data.get(INFO_RETURN))
    if editing and message.text == keyboards.CANCEL_TEXT:
        await message.reply_text(
            "تغییری ایجاد نشد.", reply_markup=ReplyKeyboardRemove()
        )
        return await _back_from_info(update, context)
    phone = normalize_phone(
        message.contact.phone_number if message.contact else message.text
    )
    if phone is None:
        await message.reply_text(
            "شماره تماس معتبر نیست. دوباره وارد کنید:",
            reply_markup=keyboards.contact_request(cancel=editing),
        )
        return PHONE
    if editing:
        return await _update_info(update, context, phone=phone)
    context.user_data["phone"] = phone
    repository.save_customer(_customer(update, context))
    # An inline keyboard and ReplyKeyboardRemove can't share one message.
    await message.reply_text(
        "✅ نام، شرکت و شماره شما ذخیره شد و در سفارش‌های بعدی دوباره پرسیده نمی‌شود."
        "\n(با دستور /profile در منوی ربات می‌توانید آن‌ها را تغییر دهید.)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _continue_checkout(update, context)


async def _ask_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saved addresses as buttons, if any; a new one can always be typed."""
    addresses = repository.get_addresses(_chat_id(update))
    context.user_data["addresses"] = addresses
    if not addresses:
        await _send(update, ASK_ADDRESS)
    else:
        await _send(
            update,
            "📍 آدرس تحویل را انتخاب کنید، یا آدرس جدید را بنویسید:",
            keyboards.addresses(addresses),
        )
    return ADDRESS


async def choose_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    index = query.data.removeprefix(keyboards.ADDRESS_PREFIX)
    addresses = context.user_data.get("addresses", [])
    if not index.isdigit() or int(index) >= len(addresses):
        await query.answer("این آدرس دیگر در دسترس نیست.", show_alert=True)
        return ADDRESS
    context.user_data["address"] = addresses[int(index)]
    await query.answer()
    return await _show_summary(update, context)


async def ask_new_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        ASK_ADDRESS, reply_markup=keyboards.back(keyboards.ADDRESS_LIST)
    )
    return ADDRESS


async def show_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _ask_address(update, context)


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
    customer = _customer(update, context)
    # Not confirmed yet, so it's added on top of the open orders.
    minutes = _open_orders_minutes() + sum(item.total_minutes for item in items)
    discount = _order_discount(context, customer.chat_id, items)
    summary = order_summary(customer, items, address, discount)
    text = "\n".join(
        ["📋 خلاصه سفارش", "", *summary, "", *_estimate_lines(minutes, address)]
    )
    await _send(update, text, keyboards.confirm())
    return CONFIRM


# ---------- saved name and phone ----------


def _profile_view(chat_id: str) -> tuple[str, InlineKeyboardMarkup]:
    customer = repository.get_customer(chat_id)
    if customer is None:
        return (
            (
                "👤 اطلاعات من\n\nهنوز اطلاعاتی ثبت نشده است."
                "\nنام، شرکت و شماره شما در اولین سفارش ذخیره می‌شود."
            ),
            keyboards.profile(known=False),
        )
    lines = [
        "👤 اطلاعات من",
        "",
        f"👤 نام: {customer.name}",
        f"🏢 شرکت: {customer.company or 'ثبت نشده'}",
        f"📞 تماس: {customer.phone}",
    ]
    if addresses := repository.get_addresses(chat_id):
        lines += ["", "📍 آدرس‌های قبلی:", *(f"• {address}" for address in addresses)]
    return "\n".join(lines), keyboards.profile(known=True)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/profile, or 🔙 from changing the name or company."""
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop(INFO_RETURN, None)
    text, markup = _profile_view(_chat_id(update))
    await _send(update, text, markup)
    return MENU


def _info_target(query_data: str) -> str:
    from_summary = query_data in (
        keyboards.EDIT_NAME,
        keyboards.EDIT_COMPANY,
        keyboards.EDIT_PHONE,
    )
    return "summary" if from_summary else "profile"


async def ask_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """✏️ from the profile or from the order summary."""
    return await _ask_new_text(update, context, "name", NAME)


async def ask_new_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """🏢 from the profile or from the order summary."""
    return await _ask_new_text(update, context, "company", COMPANY)


async def _ask_new_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, field: str, state: int
) -> int:
    query = update.callback_query
    customer = repository.get_customer(_chat_id(update))
    if customer is None:
        await query.answer("هنوز اطلاعاتی ثبت نشده است.", show_alert=True)
        return MENU
    target = _info_target(query.data)
    context.user_data[INFO_RETURN] = target
    await query.answer()
    back = keyboards.SUMMARY if target == "summary" else keyboards.PROFILE
    label = INFO_LABELS[field]
    current = getattr(customer, field) or "ثبت نشده"
    await query.edit_message_text(
        f"✏️ {label} جدید را وارد کنید:\n({label} فعلی: {current})",
        reply_markup=keyboards.back(back),
    )
    return state


async def ask_new_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """📞 from the profile or from the order summary."""
    query = update.callback_query
    customer = repository.get_customer(_chat_id(update))
    if customer is None:
        await query.answer("هنوز اطلاعاتی ثبت نشده است.", show_alert=True)
        return MENU
    context.user_data[INFO_RETURN] = _info_target(query.data)
    await query.answer()
    # The contact button needs a reply keyboard, which only a new message can carry.
    await query.edit_message_reply_markup(None)
    await context.bot.send_message(
        update.effective_chat.id,
        f"📞 شماره جدید را وارد کنید یا از دکمه زیر استفاده کنید:"
        f"\n(شماره فعلی: {customer.phone})",
        reply_markup=keyboards.contact_request(cancel=True),
    )
    return PHONE


async def _update_info(
    update: Update, context: ContextTypes.DEFAULT_TYPE, **changes: str
) -> int:
    """Save a new name, company or phone, then go back to where it was changed from."""
    customer = repository.get_customer(_chat_id(update))
    if customer is None:
        context.user_data.pop(INFO_RETURN, None)
        await update.message.reply_text(CHOOSE_CATEGORY, reply_markup=_main_menu())
        return MENU
    customer = replace(customer, **changes)
    repository.save_customer(customer)
    _remember(context, customer)
    first_time = context.user_data.get(INFO_RETURN) == "checkout"
    await update.message.reply_text(
        f"✅ {INFO_LABELS[next(iter(changes))]}"
        f" {'ثبت شد' if first_time else 'به‌روزرسانی شد'}.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _back_from_info(update, context)


async def _back_from_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = context.user_data.pop(INFO_RETURN, None)
    if target == "summary":
        return await _show_summary(update, context)
    if target == "checkout":
        return await _continue_checkout(update, context)
    text, markup = _profile_view(_chat_id(update))
    await _send(update, text, markup)
    return MENU


# ---------- confirmation ----------


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Customer finished the order: send it to the admin for approval."""
    query = update.callback_query
    customer = _customer(update, context)
    items = list(_cart(context).values())
    address = _address(context)
    discount = _order_discount(context, customer.chat_id, items)
    summary = order_summary(customer, items, address, discount)
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
        items, customer, address, admin_text, message.message_id, discount
    )
    context.user_data.clear()
    return ConversationHandler.END


def _telegram_user(user: User) -> str:
    username = f" @{user.username}" if user.username else ""
    return f"{user.full_name}{username} ({user.id})"


async def edit_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """✏️ on the summary: choose what to change."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ کدام مورد را می‌خواهید تغییر دهید؟", reply_markup=keyboards.edit_menu()
    )
    return CONFIRM


async def edit_receive_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(ASK_RECEIVE, reply_markup=keyboards.receive_method())
    return RECEIVE


async def back_to_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data.pop(INFO_RETURN, None)
    data = context.user_data
    if not ({"delivery", "name", "company", "phone"} <= data.keys() and _cart(context)):
        await query.answer("این دکمه دیگر فعال نیست.", show_alert=True)
        return MENU
    await query.answer()
    return await _show_summary(update, context)


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
            pending.items,
            pending.customer,
            pending.address,
            OrderState.CONFIRMED,
            pending.discount,
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
    summary = order_summary(order.customer, order.items, order.address, order.discount)
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
    summary = order_summary(
        pending.customer, pending.items, pending.address, pending.discount
    )
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


# ---------- poll ----------

# user_data keys: the answers so far (index in POLL.questions -> option or typed
# text), and the index of the question waiting for a typed answer.
POLL_ANSWERS = "poll_answers"
POLL_TYPING = "poll_typing"
MAX_POLL_TEXT = 1000
POLL_DONE = "🙏 شما قبلاً در این نظرسنجی شرکت کرده‌اید. از همراهی‌تان ممنونیم."


def _poll_text(index: int) -> str:
    section, question = POLL.questions[index]
    number = fa_digits(index + 1)
    lines = [
        f"📝 {POLL.title} (سؤال {number} از {fa_digits(len(POLL.questions))})",
        "",
    ]
    if section.title:
        lines.append(f"🔹 {section.title}")
        if section.description:
            lines.append(section.description)
        lines.append("")
    lines.append(f"{number}. {question.text}")
    if not question.options:
        lines += ["", "✍️ پاسخ خود را بنویسید و ارسال کنید."]
    return "\n".join(lines)


def _poll_question(index: str) -> PollQuestion | None:
    """The question at this index of POLL.questions, from callback data."""
    if not index.isdigit() or int(index) >= len(POLL.questions):
        return None
    return POLL.questions[int(index)][1]


async def _show_poll_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE, index: int
) -> int:
    question = POLL.questions[index][1]
    if question.options:
        selected = context.user_data[POLL_ANSWERS].get(index)
        markup = keyboards.poll_options(index, question.options, selected)
        await _send(update, _poll_text(index), markup)
        return MENU
    context.user_data[POLL_TYPING] = index
    markup = keyboards.poll_typed(index, question.optional)
    await _send(update, _poll_text(index), markup)
    return POLL_TEXT


async def open_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/poll, or /start poll: from the first unanswered question."""
    query = update.callback_query
    if repository.has_poll_response(POLL.key, _chat_id(update)):
        if query:
            await query.answer(POLL_DONE, show_alert=True)
        else:
            await update.message.reply_text(POLL_DONE)
        return MENU
    if query:
        await query.answer()
    answers = context.user_data.setdefault(POLL_ANSWERS, {})
    index = next((i for i in range(len(POLL.questions)) if i not in answers), 0)
    return await _show_poll_question(update, context, index)


async def answer_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data.removeprefix(keyboards.POLL_ANSWER_PREFIX)
    index, _, option = data.partition(":")
    question = _poll_question(index)
    answers = context.user_data.get(POLL_ANSWERS)
    if (
        answers is None  # e.g. the bot restarted, or the poll was already saved
        or question is None
        or not option.isdigit()
        or int(option) >= len(question.options)
    ):
        return await open_poll(update, context)
    await query.answer()
    answers[int(index)] = question.options[int(option)]
    return await _next_poll_step(update, context, int(index) + 1)


async def show_poll_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """🔙 in the poll: the question in the callback data."""
    query = update.callback_query
    index = query.data.removeprefix(keyboards.POLL_QUESTION_PREFIX)
    if POLL_ANSWERS not in context.user_data or _poll_question(index) is None:
        return await open_poll(update, context)
    await query.answer()
    return await _show_poll_question(update, context, int(index))


async def skip_poll_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    index = query.data.removeprefix(keyboards.POLL_SKIP_PREFIX)
    question = _poll_question(index)
    answers = context.user_data.get(POLL_ANSWERS)
    if answers is None or question is None or not question.optional:
        return await open_poll(update, context)
    await query.answer()
    answers.pop(int(index), None)
    return await _next_poll_step(update, context, int(index) + 1)


async def receive_poll_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    index = context.user_data.get(POLL_TYPING)
    answers = context.user_data.get(POLL_ANSWERS)
    if index is None or answers is None:
        await update.message.reply_text(CHOOSE_CATEGORY, reply_markup=_main_menu())
        return MENU
    value = update.message.text.strip()
    if len(value) > MAX_POLL_TEXT:
        await update.message.reply_text(
            f"پاسخ حداکثر می‌تواند {fa_digits(MAX_POLL_TEXT)} حرف باشد."
            " لطفاً کوتاه‌تر بنویسید:"
        )
        return POLL_TEXT
    del context.user_data[POLL_TYPING]
    answers[index] = value
    return await _next_poll_step(update, context, index + 1)


async def _next_poll_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, index: int
) -> int:
    """The question at index, or save the poll after the last one."""
    if index < len(POLL.questions):
        return await _show_poll_question(update, context, index)
    return await _finish_poll(update, context)


async def _finish_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers = context.user_data[POLL_ANSWERS]
    questions = [question for _, question in POLL.questions]
    missing = next(
        (
            index
            for index, question in enumerate(questions)
            if not question.optional and index not in answers
        ),
        None,
    )
    if missing is not None:  # an old question message was answered out of order
        return await _show_poll_question(update, context, missing)
    user = update.effective_user
    response = PollResponse(
        poll=POLL.key,
        chat_id=_chat_id(update),
        telegram_name=user.full_name,
        telegram_username=user.username,
        answers=[
            PollAnswer(index + 1, question.text, answers[index])
            for index, question in enumerate(questions)
            if index in answers
        ],
    )
    try:
        saved = repository.save_poll_response(response)
    except Exception:
        log.exception("Could not save the poll of chat %s", response.chat_id)
        # The answers are kept, so the last question can be sent again.
        await _send(
            update,
            "ثبت پاسخ‌ها انجام نشد. لطفاً چند لحظه بعد دوباره تلاش کنید.",
            keyboards.back(f"{keyboards.POLL_QUESTION_PREFIX}{len(questions) - 1}"),
        )
        return MENU
    context.user_data.pop(POLL_ANSWERS)
    context.user_data.pop(POLL_TYPING, None)
    if saved:
        log.info("Poll %s answered by chat %s", POLL.key, response.chat_id)
        note = "🙏 ممنون که در نظرسنجی ناشتایی شرکت کردید. پاسخ‌های شما ثبت شد."
    else:
        note = POLL_DONE
    await _send(update, note)
    return MENU


# ---------- referral plan ----------


def _join_with_code(context: ContextTypes.DEFAULT_TYPE, chat_id: str, code: str) -> str:
    """Record the invite link the user started the bot with; what to tell them."""
    discount = f"{format_price(_plan(context).first_buy_discount)} تومان"
    match repository.add_referral(code, chat_id):
        case JoinResult.JOINED:
            log.info("Chat %s joined with invite code %s", chat_id, code)
            return (
                "🎁 با لینک دعوت دوستتان وارد شدید؛"
                f" {discount} تخفیف اولین خرید برای شما فعال شد."
            )
        case JoinResult.ALREADY_INVITED:
            if repository.first_buy_discount_due(chat_id):
                return f"🎁 تخفیف اولین خرید شما ({discount}) فعال است."
            return ""
        case JoinResult.OWN_CODE:
            return "🔗 این لینک دعوت خودتان است؛ آن را برای دوستانتان بفرستید."
        case JoinResult.ALREADY_BOUGHT:
            return "لینک دعوت برای کسانی است که هنوز از ناشتایی خرید نکرده‌اند."
        case JoinResult.UNKNOWN_CODE:
            return "⚠️ این لینک دعوت معتبر نیست."


def _plan_lines(plan: ReferralPlan) -> list[str]:
    counted = "خرید کنند" if plan.reward_on_purchase else "وارد ناشتایی شوند"
    return [
        "🎁 طرح دعوت از دوستان ناشتایی",
        "",
        (
            "بعد از اولین خرید، یک لینک دعوت اختصاصی می‌گیرید؛"
            " آن را برای دوستان و همکارانتان بفرستید:"
        ),
        (
            "• هر کس با لینک شما وارد ناشتایی شود، در اولین خریدش"
            f" {format_price(plan.first_buy_discount)} تومان تخفیف می‌گیرد."
        ),
        (
            f"• به ازای هر {fa_digits(plan.reward_every)} نفر از دعوت‌شدگانتان که"
            f" {counted}، {format_price(plan.reward_discount)} تومان تخفیف"
            " برای خرید بعدی شما ثبت می‌شود."
        ),
        (
            "• تخفیف شما خودکار روی سفارش بعدی‌تان اعمال می‌شود؛"
            " اگر از مبلغ سفارش بیشتر باشد، باقی‌مانده برای سفارش‌های بعدی می‌ماند."
        ),
        "• لینک دعوت فقط برای کسانی است که هنوز از ناشتایی خرید نکرده‌اند.",
    ]


def _referral_view(
    context: ContextTypes.DEFAULT_TYPE, chat_id: str
) -> tuple[str, InlineKeyboardMarkup]:
    plan = _plan(context)
    lines = _plan_lines(plan)
    code = repository.issue_referral_code(chat_id)
    if code is None:
        lines += ["", "🔒 لینک دعوت شما بعد از تأیید اولین سفارشتان فعال می‌شود."]
        if repository.first_buy_discount_due(chat_id):
            lines.append(
                "🎁 شما با لینک دعوت وارد شده‌اید و در اولین خرید"
                f" {format_price(plan.first_buy_discount)} تومان تخفیف دارید."
            )
        return "\n".join(lines), keyboards.referral(None)
    stats = repository.get_referral_stats(chat_id)
    link = (
        f"https://t.me/{context.bot.username}"
        f"?start={keyboards.REFERRAL_START_PREFIX}{code}"
    )
    next_reward = fa_digits(plan.until_next_reward(stats))
    lines += [
        "",
        "🔗 لینک دعوت شما:",
        link,
        "",
        "📊 دعوت‌های شما:",
        f"👥 وارد شده با لینک شما: {fa_digits(stats.joined)} نفر",
        f"🛍 خرید کرده‌اند: {fa_digits(stats.bought)} نفر",
        (
            f"⏳ تا تخفیف بعدی: {next_reward} خرید دیگر از دعوت‌شدگان"
            if plan.reward_on_purchase
            else f"⏳ تا تخفیف بعدی: {next_reward} نفر دیگر"
        ),
        "",
        f"💰 مجموع تخفیف کسب‌شده: {format_price(plan.reward_earned(stats))} تومان",
        f"✅ استفاده‌شده: {format_price(stats.reward_used)} تومان",
        f"🎁 قابل استفاده در خرید بعدی: {format_price(plan.reward_left(stats))} تومان",
    ]
    share_text = (
        "با این لینک وارد ربات ناشتایی شو و در اولین سفارشت"
        f" {format_price(plan.first_buy_discount)} تومان تخفیف بگیر 🌿"
    )
    return "\n".join(lines), keyboards.referral(link, share_text)


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/referral, or 🎁 in the main menu: the plan and the user's invitations."""
    if update.callback_query:
        await update.callback_query.answer()
    text, markup = _referral_view(context, _chat_id(update))
    await _send(update, text, markup)
    return MENU


# ---------- outside the conversation ----------


async def expired_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer(
        "این دکمه دیگر فعال نیست. برای شروع دوباره /start را بزنید.", show_alert=True
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/support: how to reach the cafe. Works mid-order without interrupting it."""
    support_id = context.bot_data.get("support_id")
    await update.message.reply_text(
        f"📞 پشتیبانی ناشتایی:\n{support_id}"
        if support_id
        else "پشتیبانی در حال حاضر در دسترس نیست."
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
