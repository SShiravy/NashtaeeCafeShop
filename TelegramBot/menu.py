from dataclasses import dataclass


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str
    price: int  # Toman


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    items: tuple[MenuItem, ...]


MAX_QTY = 99

CATEGORIES: dict[str, Category] = {
    category.id: category
    for category in (
        Category(
            "breakfast",
            "🍳 صبحانه",
            (
                MenuItem("neemro", "نیمرو", 180_000),
                MenuItem("omelette", "املت", 200_000),
                MenuItem("asali", "عدسی", 180_000),
                MenuItem("egg_drop", "اگ دراپ", 240_000),
                MenuItem("potato_egg", "سیب‌زمینی تخم‌مرغ", 200_000),
            ),
        ),
        Category(
            "lunch",
            "🍝 ناهار",
            (
                MenuItem("pasta_simple", "پاستا ساده", 200_000),
                MenuItem("pasta_mushroom", "پاستا با قارچ", 240_000),
                MenuItem("pasta_chicken", "پاستا با قارچ و مرغ", 295_000),
                MenuItem("special_snack", "اسنک مخصوص", 200_000),
                MenuItem("kashk_bademjan", "کشک بادمجان", 230_000),
            ),
        ),
    )
}

ITEMS: dict[str, MenuItem] = {
    item.id: item for category in CATEGORIES.values() for item in category.items
}
ITEM_CATEGORY: dict[str, str] = {
    item.id: category.id for category in CATEGORIES.values() for item in category.items
}
