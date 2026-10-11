import re

_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def fa_digits(value: object) -> str:
    return str(value).translate(_TO_FA)


def en_digits(value: object) -> str:
    """Convert Persian and Arabic-Indic digits to ASCII digits."""
    return str(value).translate(_TO_EN)


def format_price(amount: int) -> str:
    """180000 -> ۱۸۰٬۰۰۰"""
    return fa_digits(f"{amount:,}".replace(",", "٬"))


def normalize_phone(raw: str) -> str | None:
    """Return an Iranian mobile number as 09xxxxxxxxx, or None if it is invalid."""
    phone = re.sub(r"[\s\-()]", "", en_digits(raw))
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("0098"):
        phone = "0" + phone[4:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    elif phone.startswith("9") and len(phone) == 10:
        phone = "0" + phone
    return phone if re.fullmatch(r"09\d{9}", phone) else None
