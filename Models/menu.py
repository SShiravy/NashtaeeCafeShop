from dataclasses import dataclass, field


@dataclass(slots=True)
class Product:
    """
    CafeShop Products, admin defines and controls available status
    """

    name: str
    farsi_name: str
    price: int
    available: bool = field(default=True)
    prep_count: int = field(default=3)  # prepration of every 3 food takes prep_minutes
    prep_minutes: int = field(default=10)


@dataclass(slots=True)
class Item:
    product: Product
    count: int = field(default=1)
    total_minutes: int = field(default=10, init=False)

    def __post_init__(self):
        self.total_minutes = (
            int(self.count / self.product.prep_count) * self.product.prep_minutes
        )
        if self.count % self.product.prep_count:
            self.total_minutes += self.product.prep_minutes
        return self.total_minutes
