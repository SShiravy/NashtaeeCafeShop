"""Fill an empty products table with the initial menu: python -m Database.seed"""

from sqlmodel import select

from Database.database import create_db_and_tables, get_session
from Database.tables import ProductTable
from Models.menu import Product, ProductCategory

BREAKFAST = ProductCategory.BREAKFAST
LUNCH = ProductCategory.LUNCH

PRODUCTS = [
    Product("neemro", "نیمرو", 180_000, BREAKFAST, prep_minutes=10),
    Product("omelette", "املت", 200_000, BREAKFAST, prep_minutes=12),
    Product("asali", "عدسی", 180_000, BREAKFAST, prep_minutes=25),
    Product("egg_drop", "اگ دراپ", 240_000, BREAKFAST, prep_minutes=8),
    Product("potato_egg", "سیب‌زمینی تخم‌مرغ", 200_000, BREAKFAST, prep_minutes=20),
    Product("pasta_simple", "پاستا ساده", 200_000, LUNCH, prep_minutes=15),
    Product("pasta_mushroom", "پاستا با قارچ", 240_000, LUNCH, prep_minutes=15),
    Product("pasta_chicken", "پاستا با قارچ و مرغ", 295_000, LUNCH, prep_minutes=25),
    Product("special_snack", "اسنک مخصوص", 200_000, LUNCH, prep_minutes=15),
    Product("kashk_bademjan", "کشک بادمجان", 230_000, LUNCH, prep_minutes=20),
]


def seed_products() -> int:
    """Insert PRODUCTS if the table is empty; return how many were inserted."""
    create_db_and_tables()
    with get_session() as session:
        if session.exec(select(ProductTable)).first() is not None:
            return 0
        session.add_all(ProductTable.from_model(product) for product in PRODUCTS)
        session.commit()
    return len(PRODUCTS)


if __name__ == "__main__":
    count = seed_products()
    print(
        f"{count} products added" if count else "products table is not empty, skipped"
    )
