from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from Models.menu import Product, ProductCategory
from TelegramBot.utils import fa_digits, format_price

# Callback data. Prefixed values carry an id after the prefix.
MAIN = "main"
CART = "cart"
CART_CLEAR = "cart_clear"
CHECKOUT = "checkout"
CONFIRM = "confirm"
EDIT = "edit"
CANCEL = "cancel"
NEW_ORDER = "new_order"
PROFILE = "profile"
PROFILE_NAME = "profile_name"
PROFILE_PHONE = "profile_phone"
SUMMARY = "summary"  # back to the order summary
EDIT_RECEIVE = "edit_receive"
EDIT_NAME = "edit_name"
EDIT_PHONE = "edit_phone"
ADDRESS_NEW = "address_new"
ADDRESS_LIST = "address_list"
ADDRESS_PREFIX = "address:"  # address:<index in the list shown to the customer>
CATEGORY_PREFIX = "cat:"  # cat:<ProductCategory.name>
ITEM_PREFIX = "item:"  # item:<Product.name>
QTY_PREFIX = "qty:"  # qty:<Product.name>:<quantity>
CUSTOM_QTY_PREFIX = "custom_qty:"  # custom_qty:<Product.name>
RECEIVE_PREFIX = "receive:"  # receive:<PICKUP|DELIVERY>
ADMIN_CONFIRM_PREFIX = "admin_confirm:"  # admin_confirm:<pending order id>
ADMIN_CANCEL_PREFIX = "admin_cancel:"  # admin_cancel:<pending order id>

PICKUP = "pickup"
DELIVERY = "delivery"

# A reply-keyboard button, so it arrives as a text message.
CANCEL_TEXT = "🔙 انصراف"


def main_menu(categories: list[ProductCategory]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                category.value, callback_data=CATEGORY_PREFIX + category.name
            )
        ]
        for category in categories
    ]
    rows.append([InlineKeyboardButton("🛒 سبد خرید", callback_data=CART)])
    rows.append([InlineKeyboardButton("👤 اطلاعات من", callback_data=PROFILE)])
    return InlineKeyboardMarkup(rows)


def category_items(products: list[Product]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{product.farsi_name} — {format_price(product.price)} تومان",
                callback_data=ITEM_PREFIX + product.name,
            )
        ]
        for product in products
    ]
    rows.append([InlineKeyboardButton("🛒 سبد خرید", callback_data=CART)])
    rows.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data=MAIN)])
    return InlineKeyboardMarkup(rows)


def quantity(product: Product) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    fa_digits(n), callback_data=f"{QTY_PREFIX}{product.name}:{n}"
                )
                for n in range(1, 6)
            ],
            [
                InlineKeyboardButton(
                    "🔢 تعداد بیشتر", callback_data=CUSTOM_QTY_PREFIX + product.name
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت", callback_data=CATEGORY_PREFIX + product.category.name
                )
            ],
        ]
    )


def custom_quantity(product: Product) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت", callback_data=ITEM_PREFIX + product.name)]]
    )


def after_add() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ ادامه سفارش", callback_data=MAIN),
                InlineKeyboardButton("🛒 سبد خرید", callback_data=CART),
            ],
            [InlineKeyboardButton("✅ ثبت سفارش", callback_data=CHECKOUT)],
        ]
    )


def cart(has_items: bool) -> InlineKeyboardMarkup:
    if not has_items:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("🍽 مشاهده منو", callback_data=MAIN)]]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ ادامه سفارش", callback_data=MAIN),
                InlineKeyboardButton("🗑 خالی کردن سبد", callback_data=CART_CLEAR),
            ],
            [InlineKeyboardButton("✅ ثبت سفارش", callback_data=CHECKOUT)],
        ]
    )


def receive_method() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏪 حضوری", callback_data=RECEIVE_PREFIX + PICKUP),
                InlineKeyboardButton(
                    "🚚 ارسال", callback_data=RECEIVE_PREFIX + DELIVERY
                ),
            ],
            [InlineKeyboardButton("🔙 سبد خرید", callback_data=CART)],
        ]
    )


def contact_request(cancel: bool = False) -> ReplyKeyboardMarkup:
    """cancel adds a CANCEL_TEXT button, for changing a phone number already saved."""
    rows = [[KeyboardButton("📱 ارسال شماره تماس", request_contact=True)]]
    if cancel:
        rows.append([KeyboardButton(CANCEL_TEXT)])
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="09xxxxxxxxx",
    )


def confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تأیید سفارش", callback_data=CONFIRM),
                InlineKeyboardButton("✏️ ویرایش", callback_data=EDIT),
            ],
            [InlineKeyboardButton("❌ لغو", callback_data=CANCEL)],
        ]
    )


def new_order() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍽 سفارش جدید", callback_data=NEW_ORDER)]]
    )


def admin_decision(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تأیید", callback_data=ADMIN_CONFIRM_PREFIX + pending_id
                ),
                InlineKeyboardButton(
                    "❌ رد", callback_data=ADMIN_CANCEL_PREFIX + pending_id
                ),
            ]
        ]
    )


def back(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت", callback_data=callback_data)]]
    )


def edit_menu() -> InlineKeyboardMarkup:
    """What ✏️ on the order summary can change."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 روش دریافت و آدرس", callback_data=EDIT_RECEIVE)],
            [
                InlineKeyboardButton("✏️ تغییر نام", callback_data=EDIT_NAME),
                InlineKeyboardButton("📞 تغییر شماره", callback_data=EDIT_PHONE),
            ],
            [InlineKeyboardButton("🔙 بازگشت به خلاصه سفارش", callback_data=SUMMARY)],
        ]
    )


def addresses(addresses: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"📍 {address if len(address) <= 40 else address[:39] + '…'}",
                callback_data=f"{ADDRESS_PREFIX}{index}",
            )
        ]
        for index, address in enumerate(addresses)
    ]
    rows.append([InlineKeyboardButton("➕ آدرس جدید", callback_data=ADDRESS_NEW)])
    rows.append([InlineKeyboardButton("🔙 روش دریافت", callback_data=CHECKOUT)])
    return InlineKeyboardMarkup(rows)


def profile(known: bool) -> InlineKeyboardMarkup:
    rows = []
    if known:
        rows.append(
            [
                InlineKeyboardButton("✏️ تغییر نام", callback_data=PROFILE_NAME),
                InlineKeyboardButton("📞 تغییر شماره", callback_data=PROFILE_PHONE),
            ]
        )
    rows.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data=MAIN)])
    return InlineKeyboardMarkup(rows)
