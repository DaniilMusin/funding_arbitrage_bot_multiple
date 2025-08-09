import time
from decimal import Decimal
from typing import List

import pandas as pd

from hummingbot.core.data_type.common import PositionAction, OrderType
from hummingbot.core.event.events import LimitOrderStatus


class LimitOrder:
    """
    A Python data class used to store order information and it is passed around
    between connectors and strategies. It is also used in HummingSim for back testing as well.
    """
    @classmethod
    def to_pandas(cls, limit_orders: List['LimitOrder'], mid_price: float = 0.0, hanging_ids: List[str] = None,
                  end_time_order_age: int = 0) -> pd.DataFrame:
        """
        Creates a dataframe for displaying current active orders
        :param limit_orders: A list of current active LimitOrder from a single market
        :param mid_price: The mid price (between best bid and best ask) of the market
        :param hanging_ids: A list of hanging order ids if applicable
        :param end_time_order_age: The end time for order age calculation, if unspecified the current time is used.
        :return: A pandas data frame object
        """
        buys = [o for o in limit_orders if o.is_buy]
        sells = [o for o in limit_orders if not o.is_buy]
        buys.sort(key=lambda x: x.price, reverse=True)
        sells.sort(key=lambda x: x.price, reverse=True)

        orders = []
        columns = ["Order ID", "Type", "Price", "Spread", "Amount", "Age", "Hang"]
        data = []
        sells.extend(buys)

        now_timestamp = int(time.time() * 1e6) if end_time_order_age == 0 else end_time_order_age

        for order in sells:
            order_id_txt = order.client_order_id if len(order.client_order_id) <= 7 else f"...{order.client_order_id[-4:]}"
            type_txt = "buy" if order.is_buy else "sell"
            price = float(order.price)
            spread_txt = f"{(0 if mid_price == 0 else abs(float(order.price) - mid_price) / mid_price):.2%}"
            quantity = float(order.quantity)
            age_txt = "n/a"
            age_seconds = order.age_til(now_timestamp)
            if age_seconds >= 0:
                age_txt = pd.Timestamp(age_seconds, unit='s', tz='UTC').strftime('%H:%M:%S')
            hang_txt = "n/a" if hanging_ids is None else ("yes" if order.client_order_id in hanging_ids else "no")
            data.append([order_id_txt, type_txt, price, spread_txt, quantity, age_txt, hang_txt])

        return pd.DataFrame(data=data, columns=columns)

    def __init__(self,
                 client_order_id: str,
                 trading_pair: str,
                 is_buy: bool,
                 base_currency: str,
                 quote_currency: str,
                 price: Decimal,
                 quantity: Decimal,
                 filled_quantity: Decimal = Decimal("NaN"),
                 creation_timestamp: int = 0,
                 status: LimitOrderStatus = LimitOrderStatus.UNKNOWN,
                 position: PositionAction = PositionAction.NIL):
        self._client_order_id = client_order_id
        self._trading_pair = trading_pair
        self._is_buy = is_buy
        self._base_currency = base_currency
        self._quote_currency = quote_currency
        self._price = price
        self._quantity = quantity
        self._filled_quantity = filled_quantity
        self._creation_timestamp = creation_timestamp
        self._status = status
        self._position = position

    @property
    def client_order_id(self) -> str:
        return self._client_order_id

    @property
    def trading_pair(self) -> str:
        return self._trading_pair

    @property
    def is_buy(self) -> bool:
        return self._is_buy

    @property
    def base_currency(self) -> str:
        return self._base_currency

    @property
    def quote_currency(self) -> str:
        return self._quote_currency

    @property
    def price(self) -> Decimal:
        return self._price

    @property
    def quantity(self) -> Decimal:
        return self._quantity

    @property
    def filled_quantity(self) -> Decimal:
        return self._filled_quantity

    @property
    def creation_timestamp(self) -> int:
        return self._creation_timestamp

    @property
    def status(self) -> LimitOrderStatus:
        return self._status

    @property
    def position(self) -> PositionAction:
        return self._position

    def c_age_til(self, end_timestamp: int) -> int:
        """
        Calculates and returns age of the order since it was created til end_timestamp in seconds
        :param end_timestamp: The end timestamp
        :return: The age of the order in seconds
        """
        start_timestamp = 0
        if self.creation_timestamp > 0:
            start_timestamp = self.creation_timestamp
        elif len(self.client_order_id) > 16 and self.client_order_id[-16:].isnumeric():
            start_timestamp = int(self.client_order_id[-16:])
        if 0 < start_timestamp < end_timestamp:
            return int((end_timestamp - start_timestamp) / 1e6)
        else:
            return -1

    def c_age(self) -> int:
        """
        Calculates and returns age of the order since it was created til now.
        """
        return self.c_age_til(int(time.time() * 1e6))

    def age(self) -> int:
        return self.c_age()

    def age_til(self, start_timestamp: int) -> int:
        return self.c_age_til(start_timestamp)

    def order_type(self) -> OrderType:
        return OrderType.LIMIT

    def copy_with_id(self, client_order_id: str) -> 'LimitOrder':
        return LimitOrder(
            client_order_id=client_order_id,
            trading_pair=self.trading_pair,
            is_buy=self.is_buy,
            base_currency=self.base_currency,
            quote_currency=self.quote_currency,
            price=self.price,
            quantity=self.quantity,
            filled_quantity=self.filled_quantity,
            creation_timestamp=self.creation_timestamp,
            status=self.status,
            position=self.position,
        )

    def __repr__(self) -> str:
        return (f"LimitOrder('{self.client_order_id}', '{self.trading_pair}', {self.is_buy}, '{self.base_currency}', "
                f"'{self.quote_currency}', {self.price}, {self.quantity}, {self.filled_quantity}, "
                f"{self.creation_timestamp})")


def create_limit_order_from_cpp_limit_order(cpp_limit_order):
    # This is a placeholder for the C++ version
    # In the Python version, we'll just return None for now
    return None
