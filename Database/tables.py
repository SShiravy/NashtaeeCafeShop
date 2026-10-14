from typing import Optional
from Settings import timing
from datetime import datetime
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import Discount, Order, OrderState
from Models.poll import PollResponse
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class CustomerTable(SQLModel, table=True):
    __tablename__ = "customers"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str = Field(index=True)
    chat_id: str = Field(unique=True, index=True)
    company: str = Field(default="")
    # Invite link code (Models.referral), given once the customer has bought
    referral_code: str | None = Field(default=None, unique=True, index=True)

    orders: list["OrderTable"] = Relationship(back_populates="customer")

    @classmethod
    def from_model(cls, customer: Customer) -> "CustomerTable":
        return cls(
            name=customer.name,
            phone=customer.phone,
            chat_id=customer.chat_id,
            company=customer.company,
        )

    def to_model(self) -> Customer:
        return Customer(
            name=self.name,
            phone=self.phone,
            chat_id=self.chat_id,
            company=self.company,
        )


class ProductTable(SQLModel, table=True):
    __tablename__ = "products"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    farsi_name: str = Field(unique=True)
    price: int
    category: ProductCategory = Field(index=True)  # stored by name
    available: bool = Field(default=True)
    prep_count: int = Field(default=3)  # prepration of every 3 food takes prep_minutes
    prep_minutes: int = Field(default=10)

    order_items: list["OrderItemTable"] = Relationship(back_populates="product")

    @classmethod
    def from_model(cls, product: Product) -> "ProductTable":
        return cls(
            name=product.name,
            farsi_name=product.farsi_name,
            price=product.price,
            category=product.category,
            available=product.available,
            prep_count=product.prep_count,
            prep_minutes=product.prep_minutes,
        )

    def to_model(self) -> Product:
        return Product(
            name=self.name,
            farsi_name=self.farsi_name,
            price=self.price,
            category=self.category,
            available=self.available,
            prep_count=self.prep_count,
            prep_minutes=self.prep_minutes,
        )


class OrderTable(SQLModel, table=True):
    __tablename__ = "orders"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    order_number: int
    customer_id: int = Field(foreign_key="customers.id", index=True)
    address: Optional[str] = Field(default=None)  # default is reciving in CafeShop
    state: OrderState = Field(default=OrderState.PENDING, index=True)
    created_at: datetime = Field(default_factory=timing.now, index=True)
    # Models.order.Discount; the server defaults fill orders saved before them
    first_buy_discount: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    reward_discount: int = Field(default=0, sa_column_kwargs={"server_default": "0"})

    customer: CustomerTable = Relationship(back_populates="orders")
    items: list["OrderItemTable"] = Relationship(
        back_populates="order", cascade_delete=True
    )

    def to_model(self) -> Order:
        return Order(
            items=[item.to_model() for item in self.items],
            customer=self.customer.to_model(),
            order_number=self.order_number,
            address=self.address,
            state=self.state,
            created_at=self.created_at,
            discount=Discount(self.first_buy_discount, self.reward_discount),
        )


class OrderItemTable(SQLModel, table=True):
    """
    One line of an order (Models.menu.Item), links an order to a product
    """

    __tablename__ = "order_items"  # type: ignore

    order_id: int | None = Field(
        default=None, foreign_key="orders.id", primary_key=True, ondelete="CASCADE"
    )
    product_id: int = Field(foreign_key="products.id", primary_key=True)
    count: int = Field(default=1, gt=0)

    order: OrderTable = Relationship(back_populates="items")
    product: ProductTable = Relationship(back_populates="order_items")

    def to_model(self) -> Item:
        return Item(product=self.product.to_model(), count=self.count)


class ReferralTable(SQLModel, table=True):
    """
    A user who started the bot with a customer's invite link (Models.referral)
    """

    __tablename__ = "referrals"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    referrer_id: int = Field(foreign_key="customers.id", index=True)
    # The invited user; not in customers until their first order
    chat_id: str = Field(unique=True, index=True)  # only their first invite counts
    created_at: datetime = Field(default_factory=timing.now)


class PollResponseTable(SQLModel, table=True):
    """
    One user's finished poll (Models.poll.PollResponse), its answers are in poll_answers
    """

    __tablename__ = "poll_responses"  # type: ignore
    __table_args__ = (UniqueConstraint("poll", "chat_id"),)  # one response per user

    id: int | None = Field(default=None, primary_key=True)
    poll: str  # Poll.key
    chat_id: str
    telegram_name: str
    telegram_username: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=timing.now, index=True)

    answers: list["PollAnswerTable"] = Relationship(
        back_populates="response", cascade_delete=True
    )

    @classmethod
    def from_model(cls, response: PollResponse) -> "PollResponseTable":
        return cls(
            poll=response.poll,
            chat_id=response.chat_id,
            telegram_name=response.telegram_name,
            telegram_username=response.telegram_username,
            answers=[
                PollAnswerTable(
                    question_number=answer.question_number,
                    question=answer.question,
                    answer=answer.answer,
                )
                for answer in response.answers
            ],
        )


class PollAnswerTable(SQLModel, table=True):
    """
    One answer of a poll response, the chosen option or the typed text
    """

    __tablename__ = "poll_answers"  # type: ignore

    response_id: int | None = Field(
        default=None,
        foreign_key="poll_responses.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    question_number: int = Field(primary_key=True)
    question: str
    answer: str

    response: PollResponseTable = Relationship(back_populates="answers")
