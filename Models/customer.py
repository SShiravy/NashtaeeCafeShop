from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Customer:
    name: str
    phone: str
    chat_id: str
    company: str = ""  # empty for customers saved before it was asked
