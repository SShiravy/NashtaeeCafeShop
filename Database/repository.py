"""Database access for the bot; takes and returns Models dataclasses, never table rows."""

from sqlmodel import func, select

from Database.database import get_session
from Database.tables import CustomerTable, OrderItemTable, OrderTable, ProductTable
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import Order, OrderState


def get_products() -> list[Product]:
    """Available products, in the order they were added."""
    with get_session() as session:
        rows = session.exec(
            select(ProductTable)
            .where(ProductTable.available == True)
            .order_by(ProductTable.id)
        ).all()
        return [row.to_model() for row in rows]


def get_categories() -> list[ProductCategory]:
    """Categories that have at least one available product, in enum order."""
    in_use = {product.category for product in get_products()}
    return [category for category in ProductCategory if category in in_use]


def get_product(name: str) -> Product | None:
    """The product if it exists and is available."""
    with get_session() as session:
        row = session.exec(
            select(ProductTable).where(
                ProductTable.name == name,
                ProductTable.available == True,
            )
        ).first()
        return row.to_model() if row else None


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
