from Models.customer import Customer
from Models.menu import Food
from dataclasses import dataclass,field
from enum import Enum

class OrderState(Enum):
    PENDING="در حال بررسی" # waiting for admin to confirm
    CONFIRMED="تایید شده" # preparing the order
    FINISHED="اتمام پخت" # order is prepared 
    CANCELED="کنسل شده" # admin/customer canceled the order


@dataclass(slots=True)
class Order:
    foods:list[Food]
    customer:Customer
    order_number:int
    address:str=field(default="حضوری") # default is reciving in CafeShop
    state:OrderState=field(default=OrderState.PENDING)

