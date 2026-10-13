from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from Models.menu import Product, ProductCategory
from TelegramBot.utils import fa_digits, format_price

# Callback data, all under "adm:" so it never collides with the customer side.
HOME = "adm:home"
NEW = "adm:new"
NEW_SAVE = "adm:new_save"
CATEGORY_PREFIX = "adm:cat:"  # adm:cat:<ProductCategory.name>
PRODUCT_PREFIX = "adm:prod:"  # adm:prod:<Product.name>
TOGGLE_PREFIX = "adm:toggle:"  # adm:toggle:<Product.name>
PRICE_PREFIX = "adm:price:"  # adm:price:<Product.name>
DELETE_PREFIX = "adm:del:"  # adm:del:<Product.name>, asks for confirmation
DELETE_CONFIRM_PREFIX = "adm:del_yes:"  # adm:del_yes:<Product.name>
NEW_CATEGORY_PREFIX = "adm:new_cat:"  # adm:new_cat:<ProductCategory.name>
ORDERS = "adm:orders"
ORDER_ACTIONS_PREFIX = "adm:ord:"  # adm:ord:<order_number>, shows finish/cancel
ORDER_FINISH_PREFIX = "adm:ord_done:"  # adm:ord_done:<order_number>
ORDER_CANCEL_PREFIX = "adm:ord_cancel:"  # adm:ord_cancel:<order_number>, asks first
ORDER_CANCEL_CONFIRM_PREFIX = "adm:ord_cancel_yes:"  # adm:ord_cancel_yes:<number>


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def panel(counts: dict[ProductCategory, int], open_orders: int) -> InlineKeyboardMarkup:
    rows = [[_button(f"📋 سفارش‌های باز ({fa_digits(open_orders)})", ORDERS)]]
    rows += [
        [
            _button(
                f"{category.value} ({fa_digits(counts.get(category, 0))})",
                CATEGORY_PREFIX + category.name,
            )
        ]
        for category in ProductCategory
    ]
    rows.append([_button("➕ محصول جدید", NEW)])
    return InlineKeyboardMarkup(rows)


def category(products: list[Product]) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                f"{'🟢' if product.available else '🔴'} {product.farsi_name}"
                f" — {format_price(product.price)} تومان",
                PRODUCT_PREFIX + product.name,
            )
        ]
        for product in products
    ]
    rows.append([_button("➕ محصول جدید", NEW)])
    rows.append([_button("🔙 بازگشت", HOME)])
    return InlineKeyboardMarkup(rows)


def product(product: Product) -> InlineKeyboardMarkup:
    toggle = "🔴 ناموجود کن" if product.available else "🟢 موجود کن"
    return InlineKeyboardMarkup(
        [
            [
                _button("✏️ ویرایش قیمت", PRICE_PREFIX + product.name),
                _button(toggle, TOGGLE_PREFIX + product.name),
            ],
            [_button("🗑 حذف", DELETE_PREFIX + product.name)],
            [_button("🔙 بازگشت", CATEGORY_PREFIX + product.category.name)],
        ]
    )


def confirm_delete(product: Product) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _button("✅ بله، حذف شود", DELETE_CONFIRM_PREFIX + product.name),
                _button("❌ انصراف", PRODUCT_PREFIX + product.name),
            ]
        ]
    )


def cancel(back_to: str) -> InlineKeyboardMarkup:
    """A single cancel button for text prompts; back_to is the callback to return to."""
    return InlineKeyboardMarkup([[_button("❌ انصراف", back_to)]])


def new_category() -> InlineKeyboardMarkup:
    rows = [
        [_button(category.value, NEW_CATEGORY_PREFIX + category.name)]
        for category in ProductCategory
    ]
    rows.append([_button("❌ انصراف", HOME)])
    return InlineKeyboardMarkup(rows)


def confirm_new() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_button("✅ ثبت محصول", NEW_SAVE), _button("❌ انصراف", HOME)]]
    )


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button("🔙 پنل مدیریت", HOME)]])


def order_actions(order_number: int) -> InlineKeyboardMarkup:
    """Buttons of a confirmed order: finish it, or cancel it (asks first)."""
    return InlineKeyboardMarkup(
        [
            [
                _button("🏁 اتمام پخت", f"{ORDER_FINISH_PREFIX}{order_number}"),
                _button("❌ لغو سفارش", f"{ORDER_CANCEL_PREFIX}{order_number}"),
            ]
        ]
    )


def confirm_cancel_order(order_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _button(
                    "⚠️ بله، سفارش لغو شود",
                    f"{ORDER_CANCEL_CONFIRM_PREFIX}{order_number}",
                ),
                _button("🔙 بازگشت", f"{ORDER_ACTIONS_PREFIX}{order_number}"),
            ]
        ]
    )
