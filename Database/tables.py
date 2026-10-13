from typing import Optional
from Settings import timing
from datetime import datetime
from Models.customer import Customer
from Models.menu import Item, Product, ProductCategory
from Models.order import Order, OrderState
from sqlmodel import Field, Relationship, SQLModel


class CustomerTable(SQLModel, table=True):
    __tablename__ = "customers"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str = Field(index=True)
    chat_id: str = Field(unique=True, index=True)

    orders: list["OrderTable"] = Relationship(back_populates="customer")

    @classmethod
    def from_model(cls, customer: Customer) -> "CustomerTable":
        return cls(
            name=customer.name,
            phone=customer.phone,
            chat_id=customer.chat_id,
        )

    def to_model(self) -> Customer:
        return Customer(
            name=self.name,
            phone=self.phone,
            chat_id=self.chat_id,
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
