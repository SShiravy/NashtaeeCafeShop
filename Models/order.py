from typing import Optional

from Settings import timing
from Models.customer import Customer
from Models.menu import Item
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderState(Enum):
    PENDING = "در حال بررسی"  # waiting for admin to confirm
    CONFIRMED = "تایید شده"  # preparing the order
    FINISHED = "اتمام پخت"  # order is prepared
    CANCELED = "کنسل شده"  # admin/customer canceled the order


@dataclass(slots=True, frozen=True)
class Discount:
    """Referral discounts of an order in toman (see Models.referral)."""

    first_buy: int = 0  # an invited customer's first order
    reward: int = 0  # earned by inviting others

    @property
    def total(self) -> int:
        return self.first_buy + self.reward


NO_DISCOUNT = Discount()


@dataclass(slots=True)
class Order:
    items: list[Item]
    customer: Customer
    order_number: int
    address: Optional[str] = field(default=None)  # default is reciving in CafeShop
    state: OrderState = field(default=OrderState.PENDING)
    created_at: datetime = field(default_factory=timing.now)
    discount: Discount = field(default_factory=Discount)
