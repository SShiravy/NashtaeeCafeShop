"""Database access for the bot; takes and returns Models dataclasses, never table rows."""

import secrets
import string
from dataclasses import asdict

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, or_, select

from Database.database import get_session
from Database.tables import (
    CustomerTable,
    OrderItemTable,
    OrderTable,
    PollResponseTable,
    ProductTable,
    ReferralTable,
)
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import NO_DISCOUNT, Discount, Order, OrderState
from Models.poll import PollResponse
from Models.referral import JoinResult, ReferralStats

REFERRAL_CODE_LENGTH = 8
REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits


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
    discount: Discount = NO_DISCOUNT,
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
            first_buy_discount=discount.first_buy,
            reward_discount=discount.reward,
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


def has_poll_response(poll: str, chat_id: str) -> bool:
    """Whether this chat already finished the poll with this key."""
    with get_session() as session:
        row = session.exec(
            select(PollResponseTable.id).where(
                PollResponseTable.poll == poll, PollResponseTable.chat_id == chat_id
            )
        ).first()
        return row is not None


def save_poll_response(response: PollResponse) -> bool:
    """Save a finished poll; False, saving nothing, if the chat already answered it."""
    if has_poll_response(response.poll, response.chat_id):
        return False
    with get_session() as session:
        session.add(PollResponseTable.from_model(response))
        session.commit()
    return True


# ---------- referral plan ----------
# A customer "has bought" once they have an order that wasn't canceled, so
# canceling an order gives back the referral discounts it used.


def _buyers():
    """Chat ids of the customers who have bought."""
    return (
        select(CustomerTable.chat_id)
        .join(OrderTable)
        .where(OrderTable.state != OrderState.CANCELED)
    )


def _has_bought(session: Session, chat_id: str) -> bool:
    row = session.exec(_buyers().where(CustomerTable.chat_id == chat_id)).first()
    return row is not None


def _new_referral_code(session: Session) -> str:
    while True:
        code = "".join(
            secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH)
        )
        taken = session.exec(
            select(CustomerTable.id).where(CustomerTable.referral_code == code)
        ).first()
        if taken is None:
            return code


def issue_referral_code(chat_id: str) -> str | None:
    """The customer's invite code, made the first time; None until they have bought."""
    with get_session() as session:
        row = session.exec(
            select(CustomerTable).where(CustomerTable.chat_id == chat_id)
        ).first()
        if row is None:
            return None
        if row.referral_code is None:
            if not _has_bought(session, chat_id):
                return None
            row.referral_code = _new_referral_code(session)
            session.add(row)
            session.commit()
        return row.referral_code


def add_referral(code: str, chat_id: str) -> JoinResult:
    """Record that chat_id started the bot with the customer's invite code."""
    with get_session() as session:
        referrer = session.exec(
            select(CustomerTable).where(CustomerTable.referral_code == code)
        ).first()
        if referrer is None:
            return JoinResult.UNKNOWN_CODE
        if referrer.chat_id == chat_id:
            return JoinResult.OWN_CODE
        invited = session.exec(
            select(ReferralTable.id).where(ReferralTable.chat_id == chat_id)
        ).first()
        if invited is not None:
            return JoinResult.ALREADY_INVITED
        if _has_bought(session, chat_id):
            return JoinResult.ALREADY_BOUGHT
        session.add(ReferralTable(referrer_id=referrer.id, chat_id=chat_id))
        try:
            session.commit()
        except IntegrityError:  # the same chat was recorded in the meantime
            return JoinResult.ALREADY_INVITED
        return JoinResult.JOINED


def first_buy_discount_due(chat_id: str) -> bool:
    """Whether the chat joined with an invite link and hasn't bought yet."""
    with get_session() as session:
        invited = session.exec(
            select(ReferralTable.id).where(ReferralTable.chat_id == chat_id)
        ).first()
        return invited is not None and not _has_bought(session, chat_id)


def get_referral_stats(chat_id: str) -> ReferralStats:
    """The users the customer invited, and the reward discount they used so far."""
    with get_session() as session:
        customer_id = session.exec(
            select(CustomerTable.id).where(CustomerTable.chat_id == chat_id)
        ).first()
        if customer_id is None:
            return ReferralStats(joined=0, bought=0, reward_used=0)
        invited = ReferralTable.referrer_id == customer_id
        joined = session.exec(select(func.count(ReferralTable.id)).where(invited)).one()
        bought = session.exec(
            select(func.count(ReferralTable.id)).where(
                invited, col(ReferralTable.chat_id).in_(_buyers())
            )
        ).one()
        reward_used = session.exec(
            select(func.coalesce(func.sum(OrderTable.reward_discount), 0)).where(
                OrderTable.customer_id == customer_id,
                OrderTable.state != OrderState.CANCELED,
            )
        ).one()
        return ReferralStats(joined=joined, bought=bought, reward_used=reward_used)
