import asyncio
from decimal import Decimal
from typing import Dict, List, Mapping, Optional, TYPE_CHECKING

from bidict import bidict

from hummingbot.connector.budget_checker import BudgetChecker
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_query_result import ClientOrderBookQueryResult
from hummingbot.core.data_type.order_book_tracker import OrderBookTracker
from hummingbot.core.utils.async_utils import safe_gather

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

s_float_NaN = float("nan")
s_decimal_NaN = Decimal("nan")
s_decimal_0 = Decimal(0)


class ExchangeBase(ConnectorBase):
    """
    ExchangeBase provides common exchange (for both centralized and decentralized) connector functionality and
    interface.
    """

    def __init__(self, client_config_map: "ClientConfigAdapter"):
        super().__init__(client_config_map)
        self._order_book_tracker = None
        self._budget_checker = BudgetChecker(exchange=self)
        self._trading_pair_symbol_map: Optional[Mapping[str, str]] = None
        self._mapping_initialization_lock = asyncio.Lock()

    @staticmethod
    def convert_from_exchange_trading_pair(exchange_trading_pair: str) -> Optional[str]:
        return exchange_trading_pair

    @staticmethod
    def convert_to_exchange_trading_pair(hb_trading_pair: str) -> str:
        return hb_trading_pair

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        raise NotImplementedError

    @property
    def limit_orders(self) -> List[LimitOrder]:
        raise NotImplementedError

    @property
    def budget_checker(self) -> BudgetChecker:
        return self._budget_checker

    @property
    def order_book_tracker(self) -> Optional[OrderBookTracker]:
        return self._order_book_tracker

    async def trading_pair_symbol_map(self):
        if not self.trading_pair_symbol_map_ready():
            async with self._mapping_initialization_lock:
                if not self.trading_pair_symbol_map_ready():
                    await self._initialize_trading_pair_symbol_map()
        current_map = self._trading_pair_symbol_map or bidict()
        return current_map

    def trading_pair_symbol_map_ready(self):
        """
        Checks if the mapping from exchange symbols to client trading pairs has been initialized

        :return: True if the mapping has been initialized, False otherwise
        """
        return self._trading_pair_symbol_map is not None and len(self._trading_pair_symbol_map) > 0

    async def all_trading_pairs(self) -> List[str]:
        """
        List of all trading pairs supported by the connector

        :return: List of trading pair symbols in the Hummingbot format
        """
        mapping = await self.trading_pair_symbol_map()
        return list(mapping.values())

    async def exchange_symbol_associated_to_pair(self, trading_pair: str) -> str:
        """
        Used to translate a trading pair from the client notation to the exchange notation

        :param trading_pair: trading pair in client notation

        :return: trading pair in exchange notation
        """
        symbol_map = await self.trading_pair_symbol_map()
        return symbol_map.inverse[trading_pair]

    async def trading_pair_associated_to_exchange_symbol(self, symbol: str,) -> str:
        """
        Used to translate a trading pair from the exchange notation to the client notation

        :param symbol: trading pair in exchange notation

        :return: trading pair in client notation
        """
        symbol_map = await self.trading_pair_symbol_map()
        return symbol_map[symbol]

    async def get_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, float]:
        """
        Return a dictionary the trading_pair as key and the current price as value for each trading pair passed as
        parameter

        :param trading_pairs: list of trading pairs to get the prices for

        :return: Dictionary of associations between token pair and its latest price
        """
        tasks = [self._get_last_traded_price(trading_pair=trading_pair) for trading_pair in trading_pairs]
        results = await safe_gather(*tasks)
        return {t_pair: result for t_pair, result in zip(trading_pairs, results)}

    def get_mid_price(self, trading_pair: str) -> Decimal:
        return (self.get_price(trading_pair, True) + self.get_price(trading_pair, False)) / Decimal("2")

    def c_buy(self, trading_pair: str, amount, order_type=OrderType.MARKET,
              price=s_decimal_NaN, kwargs={}):
        return self.buy(trading_pair, amount, order_type, price, **kwargs)

    def c_sell(self, trading_pair: str, amount, order_type=OrderType.MARKET,
               price=s_decimal_NaN, kwargs={}):
        return self.sell(trading_pair, amount, order_type, price, **kwargs)

    def c_cancel(self, trading_pair: str, client_order_id: str):
        return self.cancel(trading_pair, client_order_id)

    def c_stop_tracking_order(self, order_id: str):
        raise NotImplementedError

    def c_get_fee(self,
                  base_currency: str,
                  quote_currency: str,
                  order_type,
                  order_side,
                  amount,
                  price,
                  is_maker=None):
        return self.get_fee(base_currency, quote_currency, order_type, order_side, amount, price, is_maker)

    def c_get_order_book(self, trading_pair: str):
        return self.get_order_book(trading_pair)

    def c_get_price(self, trading_pair: str, is_buy: bool):
        """
        :returns: Top bid/ask price for a specific trading pair
        """
        order_book = self.c_get_order_book(trading_pair)
        try:
            top_price = Decimal(str(order_book.c_get_price(is_buy)))
        except EnvironmentError:
            self.logger().warning(f"{'Ask' if is_buy else 'Bid'} orderbook for {trading_pair} is empty.")
            return s_decimal_NaN
        return self.c_quantize_order_price(trading_pair, top_price)

    def c_get_vwap_for_volume(self, trading_pair: str, is_buy: bool, volume):
        order_book = self.c_get_order_book(trading_pair)
        result = order_book.c_get_vwap_for_volume(is_buy, float(volume))
        query_price = Decimal(str(result.query_price))
        query_volume = Decimal(str(result.query_volume))
        result_price = Decimal(str(result.result_price))
        result_volume = Decimal(str(result.result_volume))
        return ClientOrderBookQueryResult(query_price,
                                          query_volume,
                                          result_price,
                                          result_volume)

    def c_get_price_for_quote_volume(self, trading_pair: str, is_buy: bool, volume: float):
        order_book = self.c_get_order_book(trading_pair)
        result = order_book.c_get_price_for_quote_volume(is_buy, float(volume))
        query_price = Decimal(str(result.query_price))
        query_volume = Decimal(str(result.query_volume))
        result_price = Decimal(str(result.result_price))
        result_volume = Decimal(str(result.result_volume))
        return ClientOrderBookQueryResult(query_price,
                                          query_volume,
                                          result_price,
                                          result_volume)

    def c_get_price_for_volume(self, trading_pair: str, is_buy: bool, volume):
        order_book = self.c_get_order_book(trading_pair)
        result = order_book.c_get_price_for_volume(is_buy, float(volume))
        query_price = Decimal(str(result.query_price))
        query_volume = Decimal(str(result.query_volume))
        result_price = Decimal(str(result.result_price))
        result_volume = Decimal(str(result.result_volume))
        return ClientOrderBookQueryResult(query_price,
                                          query_volume,
                                          result_price,
                                          result_volume)

    # Abstract methods that need to be implemented by subclasses
    def buy(self, trading_pair: str, amount, order_type=OrderType.MARKET, price=s_decimal_NaN, **kwargs):
        raise NotImplementedError

    def sell(self, trading_pair: str, amount, order_type=OrderType.MARKET, price=s_decimal_NaN, **kwargs):
        raise NotImplementedError

    def cancel(self, trading_pair: str, client_order_id: str):
        raise NotImplementedError

    def get_fee(self, base_currency: str, quote_currency: str, order_type, order_side, amount, price, is_maker=None):
        raise NotImplementedError

    def get_order_book(self, trading_pair: str):
        raise NotImplementedError

    def get_price(self, trading_pair: str, is_buy: bool):
        raise NotImplementedError

    def c_quantize_order_price(self, trading_pair: str, price):
        raise NotImplementedError

    async def _get_last_traded_price(self, trading_pair: str):
        raise NotImplementedError

    async def _initialize_trading_pair_symbol_map(self):
        raise NotImplementedError

    def get_maker_order_type(self):
        raise NotImplementedError
