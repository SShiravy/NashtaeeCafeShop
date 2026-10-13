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


@dataclass(slots=True)
class Order:
    items: list[Item]
    customer: Customer
    order_number: int
    address: Optional[str] = field(default=None)  # default is reciving in CafeShop
    state: OrderState = field(default=OrderState.PENDING)
    created_at: datetime = field(default_factory=timing.now)
