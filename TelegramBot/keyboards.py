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
CATEGORY_PREFIX = "cat:"  # cat:<ProductCategory.name>
ITEM_PREFIX = "item:"  # item:<Product.name>
QTY_PREFIX = "qty:"  # qty:<Product.name>:<quantity>
CUSTOM_QTY_PREFIX = "custom_qty:"  # custom_qty:<Product.name>
RECEIVE_PREFIX = "receive:"  # receive:<PICKUP|DELIVERY>
ADMIN_CONFIRM_PREFIX = "admin_confirm:"  # admin_confirm:<pending order id>
ADMIN_CANCEL_PREFIX = "admin_cancel:"  # admin_cancel:<pending order id>

PICKUP = "pickup"
DELIVERY = "delivery"


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


def contact_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 ارسال شماره تماس", request_contact=True)]],
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
