"""Referral plan: after their first purchase, customers invite others with a link.

An invited user gets first_buy_discount off their first order, and the inviter
gets reward_discount off their next orders for every reward_every invited users.
"""

from dataclasses import dataclass
from enum import Enum, auto

from Models.order import Discount


class JoinResult(Enum):
    """What starting the bot with an invite code did."""

    JOINED = auto()
    UNKNOWN_CODE = auto()
    OWN_CODE = auto()
    ALREADY_INVITED = auto()  # only the first invite link a user opens counts
    ALREADY_BOUGHT = auto()  # invite links are for users who haven't bought yet


@dataclass(slots=True, frozen=True)
class ReferralStats:
    """One customer's invitations."""

    joined: int  # users who started the bot with the customer's link
    bought: int  # of those, the ones who have bought
    reward_used: int  # toman of reward discount on the customer's own orders


@dataclass(slots=True, frozen=True)
class ReferralPlan:
    first_buy_discount: int  # d: toman off an invited user's first order
    reward_every: int  # n: invited users per reward
    reward_discount: int  # m: toman off the inviter's next orders, per reward
    reward_on_purchase: bool = True  # invited users count once they buy, not on joining

    def counted(self, stats: ReferralStats) -> int:
        """Invited users that count toward rewards."""
        return stats.bought if self.reward_on_purchase else stats.joined

    def reward_earned(self, stats: ReferralStats) -> int:
        return self.counted(stats) // self.reward_every * self.reward_discount

    def reward_left(self, stats: ReferralStats) -> int:
        """Earned and not used yet. Never negative, though it can be less than what
        was used: an invited user's canceled order takes their purchase back."""
        return max(0, self.reward_earned(stats) - stats.reward_used)

    def until_next_reward(self, stats: ReferralStats) -> int:
        return self.reward_every - self.counted(stats) % self.reward_every

    def discount(self, total: int, first_buy: bool, reward_left: int) -> Discount:
        """Discounts of an order of total toman; together never more than total.

        first_buy: whether the first-buy discount applies. reward_left: the reward
        the customer can still use; what this order doesn't use stays for later.
        """
        first = min(self.first_buy_discount, total) if first_buy else 0
        return Discount(first, max(0, min(reward_left, total - first)))
