"""Database access for the bot; takes and returns Models dataclasses, never table rows."""

from dataclasses import asdict

from sqlmodel import func, or_, select

from Database.database import get_session
from Database.tables import CustomerTable, OrderItemTable, OrderTable, ProductTable
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import Order, OrderState


def get_products(only_available: bool = True) -> list[Product]:
    """Products in the order they were added; only available ones by default."""
    query = select(ProductTable).order_by(ProductTable.id)
    if only_available:
        query = query.where(ProductTable.available == True)
    with get_session() as session:
        return [row.to_model() for row in session.exec(query).all()]


def get_categories() -> list[ProductCategory]:
    """Categories that have at least one available product, in enum order."""
    in_use = {product.category for product in get_products()}
    return [category for category in ProductCategory if category in in_use]


def get_product(name: str, only_available: bool = True) -> Product | None:
    """The product with this name; only if it's available by default."""
    query = select(ProductTable).where(ProductTable.name == name)
    if only_available:
        query = query.where(ProductTable.available == True)
    with get_session() as session:
        row = session.exec(query).first()
        return row.to_model() if row else None


def name_taken(value: str) -> bool:
    """Whether a product already uses value as its name or Farsi name."""
    with get_session() as session:
        row = session.exec(
            select(ProductTable.id).where(
                or_(ProductTable.name == value, ProductTable.farsi_name == value)
            )
        ).first()
        return row is not None


def add_product(product: Product) -> None:
    with get_session() as session:
        session.add(ProductTable.from_model(product))
        session.commit()


def update_product(product: Product) -> bool:
    """Save product's fields to the row with the same name; False if there is none."""
    with get_session() as session:
        row = session.exec(
            select(ProductTable).where(ProductTable.name == product.name)
        ).first()
        if row is None:
            return False
        row.sqlmodel_update(asdict(product))
        session.add(row)
        session.commit()
        return True


def product_in_orders(name: str) -> bool:
    """Whether any saved order contains the product (it can't be deleted then)."""
    with get_session() as session:
        row = session.exec(
            select(OrderItemTable.order_id)
            .join(ProductTable)
            .where(ProductTable.name == name)
        ).first()
        return row is not None


def delete_product(name: str) -> bool:
    """Delete a product that no order uses; False if it doesn't exist."""
    with get_session() as session:
        row = session.exec(
            select(ProductTable).where(ProductTable.name == name)
        ).first()
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def create_order(
    items: list[Item],
    customer: Customer,
    address: str | None,
    state: OrderState = OrderState.PENDING,
) -> Order:
    """Save a new order, creating or updating its customer, and return it numbered."""
    with get_session() as session:
        customer_row = session.exec(
            select(CustomerTable).where(CustomerTable.chat_id == customer.chat_id)
        ).first()
        if customer_row is None:
            customer_row = CustomerTable.from_model(customer)
        else:
            customer_row.name = customer.name
            customer_row.phone = customer.phone

        last_number = session.exec(select(func.max(OrderTable.order_number))).one()
        order_row = OrderTable(
            order_number=(last_number or 0) + 1,
            customer=customer_row,
            address=address,
            state=state,
        )
        for item in items:
            product_row = session.exec(
                select(ProductTable).where(ProductTable.name == item.product.name)
            ).one()
            order_row.items.append(
                OrderItemTable(product=product_row, count=item.count)
            )

        session.add(order_row)
        session.commit()
        session.refresh(order_row)
        return order_row.to_model()
