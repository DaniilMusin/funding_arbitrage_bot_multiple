import bisect
import logging
import time
from typing import (
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
)

import numpy as np
import pandas as pd

from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_query_result import OrderBookQueryResult
from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.logger import HummingbotLogger
from hummingbot.core.event.events import (
    OrderBookEvent,
    OrderBookTradeEvent
)
from hummingbot.core.pubsub import PubSub

ob_logger = None
NaN = float("nan")


class OrderBook(PubSub):
    ORDER_BOOK_TRADE_EVENT_TAG = OrderBookEvent.TradeEvent.value

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global ob_logger
        if ob_logger is None:
            ob_logger = logging.getLogger(__name__)
        return ob_logger

    def __init__(self, dex=False):
        super().__init__()
        self._snapshot_uid = 0
        self._last_diff_uid = 0
        self._best_bid = self._best_ask = float("NaN")
        self._last_trade_price = float("NaN")
        self._last_applied_trade = -1000.0
        self._last_trade_price_rest_updated = -1000
        self._dex = dex
        self._bid_book = []
        self._ask_book = []

    def c_apply_diffs(self, bids, asks, update_id):
        # Simplified implementation
        for bid in bids:
            self._bid_book.append(bid)
        for ask in asks:
            self._ask_book.append(ask)

        # Sort books
        self._bid_book.sort(key=lambda x: x.price, reverse=True)
        self._ask_book.sort(key=lambda x: x.price)

        # Update best prices
        if self._bid_book:
            self._best_bid = self._bid_book[0].price
        if self._ask_book:
            self._best_ask = self._ask_book[0].price

        self._last_diff_uid = update_id

    def c_apply_snapshot(self, bids, asks, update_id):
        # Simplified implementation
        self._bid_book = list(bids)
        self._ask_book = list(asks)

        # Sort books
        self._bid_book.sort(key=lambda x: x.price, reverse=True)
        self._ask_book.sort(key=lambda x: x.price)

        # Update best prices
        if self._bid_book:
            self._best_bid = self._bid_book[0].price
        if self._ask_book:
            self._best_ask = self._ask_book[0].price

        self._snapshot_uid = update_id

    def c_apply_trade(self, trade_event):
        self._last_trade_price = trade_event.price
        self._last_applied_trade = time.perf_counter()
        self.c_trigger_event(self.ORDER_BOOK_TRADE_EVENT_TAG, trade_event)

    @property
    def last_trade_price(self) -> float:
        return self._last_trade_price

    @last_trade_price.setter
    def last_trade_price(self, value: float):
        self._last_trade_price = value

    @property
    def last_applied_trade(self) -> float:
        return self._last_applied_trade

    @property
    def last_trade_price_rest_updated(self) -> float:
        return self._last_trade_price_rest_updated

    @last_trade_price_rest_updated.setter
    def last_trade_price_rest_updated(self, value: float):
        self._last_trade_price_rest_updated = value

    @property
    def snapshot_uid(self) -> int:
        return self._snapshot_uid

    @property
    def last_diff_uid(self) -> int:
        return self._last_diff_uid

    @property
    def snapshot(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        bids_rows = list(self.bid_entries())
        asks_rows = list(self.ask_entries())
        bids_df = pd.DataFrame(data=bids_rows, columns=OrderBookRow._fields, dtype="float64")
        asks_df = pd.DataFrame(data=asks_rows, columns=OrderBookRow._fields, dtype="float64")
        return bids_df, asks_df

    def apply_diffs(self, bids: List[OrderBookRow], asks: List[OrderBookRow], update_id: int):
        self.c_apply_diffs(bids, asks, update_id)

    def apply_snapshot(self, bids: List[OrderBookRow], asks: List[OrderBookRow], update_id: int):
        self.c_apply_snapshot(bids, asks, update_id)

    def apply_trade(self, trade: OrderBookTradeEvent):
        self.c_apply_trade(trade)

    def c_get_price(self, is_buy: bool) -> float:
        if is_buy:
            return self._best_ask
        else:
            return self._best_bid

    def c_get_vwap_for_volume(self, is_buy: bool, volume: float) -> OrderBookQueryResult:
        # Simplified implementation
        return OrderBookQueryResult(volume, 0.0, 0.0)

    def c_get_price_for_quote_volume(self, is_buy: bool, volume: float) -> OrderBookQueryResult:
        # Simplified implementation
        return OrderBookQueryResult(volume, 0.0, 0.0)

    def c_get_price_for_volume(self, is_buy: bool, volume: float) -> OrderBookQueryResult:
        # Simplified implementation
        return OrderBookQueryResult(volume, 0.0, 0.0)

    def bid_entries(self) -> Iterator[OrderBookRow]:
        for entry in self._bid_book:
            yield OrderBookRow(entry.price, entry.amount, entry.update_id)

    def ask_entries(self) -> Iterator[OrderBookRow]:
        for entry in self._ask_book:
            yield OrderBookRow(entry.price, entry.amount, entry.update_id)

    def c_trigger_event(self, event_tag: int, event_object):
        # Simplified implementation
        pass