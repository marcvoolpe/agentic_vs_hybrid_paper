import time
from enum import Enum
from typing import Any, Union

from .constants import C
from .utils import log_debug


class Evaluation(Enum):
    ACCEPT = 'accept'
    NOT_PROFITABLE_ON_BOTH = 'not_profitable_on_both'
    NOT_PROFITABLE_ON_PRICE = 'not_profitable_on_price'
    NOT_PROFITABLE_ON_QUANTITY = 'not_profitable_on_quantity'
    OFFER_QUANTITY = 'offer_quantity'
    OFFER_PRICE = 'offer_price'
    NOT_OFFER = 'not_offer'
    INVALID_OFFER = 'invalid_offer'

    @property
    def is_non_offer(self) -> bool:
        return self in (self.INVALID_OFFER, self.NOT_OFFER)


class Offer(dict):
    def __init__(self,
                 idx: int = -1,
                 price: float = None,
                 quantity: int = None,
                 stamp: int = None,
                 from_chat: bool = False,
                 profit_bot: int = None,
                 profit_user: int = None,
                 test: Any = None):
        stamp = stamp or int(time.time())
        dict.__init__(self, idx=idx, price=price, quantity=quantity,
                      stamp=stamp, from_chat=from_chat,
                      profit_bot=profit_bot, profit_user=profit_user,
                      test=test)
        self.idx = idx
        self.price = price
        self.quantity = quantity
        self.stamp = stamp
        self.from_chat = from_chat
        self.profit_bot = profit_bot
        self.profit_user = profit_user

    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    @property
    def is_valid(self) -> bool:
        return self.price_in_range and self.quantity_in_range

    @property
    def is_complete(self) -> bool:
        return None not in (self.price, self.quantity)

    @property
    def price_in_range(self) -> bool:
        return self.price in C.PRICE_RANGE

    @property
    def quantity_in_range(self) -> bool:
        return self.quantity in C.QUANTITY_RANGE

    def profits(self, bot_role: str, constraint_user: int, constraint_bot: int):
        """ This calculates the profits for the user and the bot """
        if not self.is_valid or None in (constraint_user, constraint_bot):
            self.profit_bot = -11
            self.profit_user = -10
            return

        args_bot = (self.price, self.quantity, constraint_bot)
        args_user = (self.price, self.quantity, constraint_user)

        if bot_role == C.ROLE_SUPPLIER_EMPLOYEE:
            self.profit_bot = self.profit_supplier(*args_bot)
            self.profit_user = self.profit_retailer(*args_user)
        else:
            self.profit_bot = self.profit_retailer(*args_bot)
            self.profit_user = self.profit_supplier(*args_user)

    def _is_price_feasible(self, params: dict[str, Any]) -> bool:
        """
        Checks if a given price allows the bot to achieve Nash profit.
        Returns: True / False
        """
        if self.price is None:
            return False

        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX

        if params['bot_is_supplier']:
            q_best = \
                d_max - (params['production_cost'] * (
                        d_max - d_min) / self.price)
            # TODO Make more clear
            ES_best = (((q_best ** 2 - d_min ** 2) / 2) +
                       q_best * (d_max - q_best)) / (d_max - d_min)

            max_profit = (
                    self.price * ES_best - params['production_cost'] * q_best)
            if max_profit < params['nash_profit']:
                log_debug(f"Price {self.price:.2f} too low. Bot (supplier) max "
                          f"profit = {max_profit:.2f} < Nash {params['nash_profit']:.2f}")
                return False
        else:
            q_best = d_max
            # TODO Make more clear
            ES_best = (((q_best ** 2 - d_min ** 2) / 2) +
                       q_best * (d_max - q_best)) / (d_max - d_min)

            max_profit = (params['market_price'] - self.price) * ES_best
            if max_profit < params['nash_profit']:
                log_debug(f"Price {self.price:.2f} too high. Bot (retail) max "
                          f"profit = {max_profit:.2f} < Nash {params['nash_profit']:.2f}")
                return False

        return True

    def _is_quantity_feasible(self, params: dict[str, Any]) -> bool:
        """
        Checks if a given quantity allows the bot to achieve Nash profit.
        Returns: True / False
        """
        if self.quantity is None:
            return False

        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX

        # TODO Make more clear
        ES = (((self.quantity ** 2 - d_min ** 2) / 2) +
              self.quantity * (d_max - self.quantity)) / (d_max - d_min)

        if params['bot_is_supplier']:
            required_price = (params['nash_profit'] +
                              params['production_cost'] * self.quantity) / ES
            if required_price < 0:
                log_debug(f"Quantity {self.quantity} requires negative price "
                          f"for Nash profit")
                return False

            if required_price >= params['market_price']:
                log_debug(f"Quantity {self.quantity} requires price "
                          f"{required_price:.2f} >= market price "
                          f"{params['market_price']:.2f}")
                return False
        else:
            max_acceptable_price = params['market_price'] - params[
                'nash_profit'] / ES
            if max_acceptable_price < params['production_cost']:
                log_debug(f"Quantity {self.quantity} requires negative price "
                          f"for Nash profit")
                return False

        return True

    def _validate_non_profitable_offer(self,
                                       params: dict[str, Any]) -> Evaluation:
        price_is_unfeasible = not self._is_price_feasible(params)
        quantity_is_unfeasible = not self._is_quantity_feasible(params)

        if quantity_is_unfeasible and price_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_BOTH
        elif price_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_PRICE
        elif quantity_is_unfeasible:
            return Evaluation.NOT_PROFITABLE_ON_QUANTITY
        else:
            raise Exception("Invalid offer but price and quantity feasible")

    def evaluate(self, constraint_user: int, constraint_bot: int,
                 bot_is_supplier: bool) -> Evaluation:
        """ This evaluates offers, both from the Human and AI """
        from .optimal import nash_bargaining_solution

        log_debug(f"[DEBUG Offer.evaluate] Offer: price = {self.price}, "
                  f"quantity = {self.quantity}, profit_bot = {self.profit_bot}, "
                  f"profit_user = {self.profit_user}, is_valid = {self.is_valid}")

        params = {
            'bot_is_supplier': bot_is_supplier,
            'nash_profit': nash_bargaining_solution(
                constraint_user, constraint_bot)['profit'],
            'production_cost': min([constraint_user, constraint_bot]),
            'market_price': max([constraint_user, constraint_bot]),
        }

        if self.profit_bot >= params['nash_profit']:
            result = Evaluation.ACCEPT

        elif self.is_valid:
            result = self._validate_non_profitable_offer(params)

        elif self.price is None and self.quantity_in_range:
            if self._is_quantity_feasible(params):
                result = Evaluation.OFFER_QUANTITY
            else:
                result = Evaluation.NOT_PROFITABLE_ON_BOTH

        elif self.quantity is None and self.price_in_range:
            if self._is_price_feasible(params):
                result = Evaluation.OFFER_PRICE
            else:
                result = Evaluation.NOT_PROFITABLE_ON_BOTH

        elif self.price is not None and not self.price_in_range:
            result = Evaluation.INVALID_OFFER
        elif self.quantity is not None and not self.quantity_in_range:
            result = Evaluation.INVALID_OFFER

        else:
            result = Evaluation.NOT_OFFER

        log_debug(f"[DEBUG Offer.evaluate] Result Evaluation: {result.value}")
        return result

    @staticmethod
    def _expected_demand(quantity: int) -> float:
        d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX
        if quantity <= d_min:
            return quantity
        if quantity >= d_max:
            return (d_min + d_max) / 2
        # TODO Make more clear
        return ((quantity ** 2 - d_min ** 2) / 2 +
                quantity * (d_max - quantity)) / (d_max - d_min)

    @classmethod
    def profit_supplier(cls, price: float, quantity: int, production_cost: int) \
            -> float:
        expected_sales = cls._expected_demand(quantity)
        return (price * expected_sales) - (production_cost * quantity)

    @classmethod
    def profit_retailer(cls, price: float, quantity: int, market_price: int) \
            -> float:
        expected_sales = cls._expected_demand(quantity)
        return (market_price - price) * expected_sales


class OfferList(list):
    def __init__(self, *args):
        list.__init__(self, *args)
        # Make sure this is always sorted on stamp
        self.sort(key=lambda o: o.stamp)
