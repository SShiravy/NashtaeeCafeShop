from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from TelegramBot.menu import CATEGORIES, ITEM_CATEGORY
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
CATEGORY_PREFIX = "cat:"  # cat:<category_id>
ITEM_PREFIX = "item:"  # item:<item_id>
QTY_PREFIX = "qty:"  # qty:<item_id>:<quantity>
CUSTOM_QTY_PREFIX = "custom_qty:"  # custom_qty:<item_id>
RECEIVE_PREFIX = "receive:"  # receive:<PICKUP|DELIVERY>

PICKUP = "pickup"
DELIVERY = "delivery"


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                category.title, callback_data=CATEGORY_PREFIX + category.id
            )
        ]
        for category in CATEGORIES.values()
    ]
    rows.append([InlineKeyboardButton("🛒 سبد خرید", callback_data=CART)])
    return InlineKeyboardMarkup(rows)


def category_items(category_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{item.name} — {format_price(item.price)} تومان",
                callback_data=ITEM_PREFIX + item.id,
            )
        ]
        for item in CATEGORIES[category_id].items
    ]
    rows.append([InlineKeyboardButton("🛒 سبد خرید", callback_data=CART)])
    rows.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data=MAIN)])
    return InlineKeyboardMarkup(rows)


def quantity(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    fa_digits(n), callback_data=f"{QTY_PREFIX}{item_id}:{n}"
                )
                for n in range(1, 6)
            ],
            [
                InlineKeyboardButton(
                    "🔢 تعداد بیشتر", callback_data=CUSTOM_QTY_PREFIX + item_id
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت", callback_data=CATEGORY_PREFIX + ITEM_CATEGORY[item_id]
                )
            ],
        ]
    )


def custom_quantity(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت", callback_data=ITEM_PREFIX + item_id)]]
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
