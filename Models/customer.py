from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Customer:
    name: str
    phone: str
    chat_id: str
