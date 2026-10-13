"""Database access for the bot; takes and returns Models dataclasses, never table rows."""

from dataclasses import asdict

from sqlmodel import col, func, or_, select

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


def get_order(order_number: int) -> Order | None:
    with get_session() as session:
        row = session.exec(
            select(OrderTable).where(OrderTable.order_number == order_number)
        ).first()
        return row.to_model() if row else None


def get_orders(state: OrderState) -> list[Order]:
    """Orders in this state, oldest first."""
    with get_session() as session:
        rows = session.exec(
            select(OrderTable)
            .where(OrderTable.state == state)
            .order_by(OrderTable.order_number)
        ).all()
        return [row.to_model() for row in rows]


def update_order_state(order_number: int, state: OrderState) -> Order | None:
    """Set the order's state and return it; None if there is no such order."""
    with get_session() as session:
        row = session.exec(
            select(OrderTable).where(OrderTable.order_number == order_number)
        ).first()
        if row is None:
            return None
        row.state = state
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def get_customer(chat_id: str) -> Customer | None:
    with get_session() as session:
        row = session.exec(
            select(CustomerTable).where(CustomerTable.chat_id == chat_id)
        ).first()
        return row.to_model() if row else None


def save_customer(customer: Customer) -> None:
    """Add the customer, or update the details of the one with the same chat_id."""
    with get_session() as session:
        row = session.exec(
            select(CustomerTable).where(CustomerTable.chat_id == customer.chat_id)
        ).first()
        if row is None:
            row = CustomerTable.from_model(customer)
        else:
            row.name = customer.name
            row.phone = customer.phone
            row.company = customer.company
        session.add(row)
        session.commit()


def get_addresses(chat_id: str, limit: int = 10) -> list[str]:
    """Distinct delivery addresses of the customer's orders, most recently used first."""
    with get_session() as session:
        rows = session.exec(
            select(OrderTable.address)
            .join(CustomerTable)
            .where(
                CustomerTable.chat_id == chat_id, col(OrderTable.address).is_not(None)
            )
            .group_by(OrderTable.address)
            .order_by(func.max(OrderTable.id).desc())
            .limit(limit)
        ).all()
        return list(rows)


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
            customer_row.company = customer.company

        last_number = session.exec(select(func.max(OrderTable.order_number))).one()
        order_row = OrderTable(
            order_number=(last_number or 0) + 1,
            customer=customer_row,
            address=address,
            state=state,
        )
        # Added before the product lookups below flush the session, so the new
        # rows linked to existing customer/product rows are already part of it.
        session.add(order_row)
        for item in items:
            product_row = session.exec(
                select(ProductTable).where(ProductTable.name == item.product.name)
            ).one()
            order_row.items.append(
                OrderItemTable(product=product_row, count=item.count)
            )

        session.commit()
        session.refresh(order_row)
        return order_row.to_model()
