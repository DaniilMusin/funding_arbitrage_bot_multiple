import datetime
import logging
import os
import time
from decimal import Decimal
from math import ceil, floor, isnan
from typing import Dict, List, Tuple, Union

import numpy as np
import pandas as pd

from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.clock import Clock

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.core.data_type.common import (
    OrderType,
    PriceType,
    TradeType
)
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils import map_df_to_str
from hummingbot.strategy.__utils__.trailing_indicators.instant_volatility import InstantVolatilityIndicator
from hummingbot.strategy.__utils__.trailing_indicators.trading_intensity import TradingIntensityIndicator
from hummingbot.strategy.avellaneda_market_making.avellaneda_market_making_config_map_pydantic import (
    AvellanedaMarketMakingConfigMap,
    DailyBetweenTimesModel,
    FromDateToDateModel,
    MultiOrderLevelModel,
    TrackHangingOrdersModel,
)
from hummingbot.strategy.conditional_execution_state import (
    RunAlwaysExecutionState,
    RunInTimeConditionalExecutionState
)
from hummingbot.strategy.data_types import (
    PriceSize,
    Proposal,
)
from hummingbot.strategy.hanging_orders_tracker import (
    CreatedPairOfOrders,
    HangingOrdersTracker,
)
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.order_book_asset_price_delegate import OrderBookAssetPriceDelegate
from hummingbot.strategy.order_tracker import OrderTracker
from hummingbot.strategy.strategy_base import StrategyBase
from hummingbot.strategy.utils import order_age

NaN = float("nan")
s_decimal_zero = Decimal(0)
s_decimal_neg_one = Decimal(-1)
s_decimal_one = Decimal(1)
pmm_logger = None


class AvellanedaMarketMakingStrategy(StrategyBase):
    OPTION_LOG_CREATE_ORDER = 1 << 3
    OPTION_LOG_MAKER_ORDER_FILLED = 1 << 4
    OPTION_LOG_STATUS_REPORT = 1 << 5
    OPTION_LOG_ALL = 0x7fffffffffffffff

    @classmethod
    def logger(cls):
        global pmm_logger
        if pmm_logger is None:
            pmm_logger = logging.getLogger(__name__)
        return pmm_logger

    def init_params(self,
                    config_map: Union[AvellanedaMarketMakingConfigMap, ClientConfigAdapter],
                    market_info: MarketTradingPairTuple,
                    logging_options: int = OPTION_LOG_ALL,
                    status_report_interval: float = 900,
                    hb_app_notification: bool = False,
                    debug_csv_path: str = '',
                    is_debug: bool = False,
                    ):
        self._sb_order_tracker = OrderTracker()
        self._config_map = config_map
        self._market_info = market_info
        self._price_delegate = OrderBookAssetPriceDelegate(market_info.market, market_info.trading_pair)
        self._hb_app_notification = hb_app_notification
        self._hanging_orders_enabled = False
        self._hanging_orders_cancel_pct = Decimal("10")
        self._hanging_orders_tracker = HangingOrdersTracker(self,
                                                            self._hanging_orders_cancel_pct / Decimal('100'))

        self._cancel_timestamp = 0
        self._create_timestamp = 0
        self._limit_order_type = self._market_info.market.get_maker_order_type()
        self._all_markets_ready = False
        self._filled_buys_balance = 0
        self._filled_sells_balance = 0
        self._logging_options = logging_options
        self._last_timestamp = 0
        self._status_report_interval = status_report_interval
        self._last_own_trade_price = Decimal('nan')

        self.c_add_markets([market_info.market])
        self._volatility_buffer_size = 0
        self._trading_intensity_buffer_size = 0
        self._ticks_to_be_ready = -1
        self._avg_vol = None
        self._trading_intensity = None
        self._last_sampling_timestamp = 0
        self._alpha = None
        self._kappa = None
        self._execution_mode = None
        self._execution_timeframe = None
        self._execution_state = None
        self._start_time = None
        self._end_time = None
        self._reservation_price = s_decimal_zero
        self._optimal_spread = s_decimal_zero
        self._optimal_ask = s_decimal_zero
        self._optimal_bid = s_decimal_zero
        self._debug_csv_path = debug_csv_path
        self._is_debug = is_debug
        try:
            if self._is_debug:
                os.unlink(self._debug_csv_path)
        except FileNotFoundError:
            pass

        self.get_config_map_execution_mode()
        self.get_config_map_hanging_orders()

    def all_markets_ready(self):
        return all([market.ready for market in self._sb_markets])

    @property
    def min_spread(self):
        return self._config_map.min_spread

    @property
    def avg_vol(self):
        return self._avg_vol

    @avg_vol.setter
    def avg_vol(self, indicator: InstantVolatilityIndicator):
        self._avg_vol = indicator

    @property
    def trading_intensity(self):
        return self._trading_intensity

    @trading_intensity.setter
    def trading_intensity(self, indicator: TradingIntensityIndicator):
        self._trading_intensity = indicator

    @property
    def market_info(self) -> MarketTradingPairTuple:
        return self._market_info

    @property
    def order_refresh_tolerance_pct(self) -> Decimal:
        return self._config_map.order_refresh_tolerance_pct

    @property
    def order_refresh_tolerance(self) -> Decimal:
        return self._config_map.order_refresh_tolerance_pct / Decimal('100')

    @property
    def order_amount(self) -> Decimal:
        return self._config_map.order_amount

    @property
    def inventory_target_base_pct(self) -> Decimal:
        return self._config_map.inventory_target_base_pct

    @property
    def inventory_target_base(self) -> Decimal:
        return self.inventory_target_base_pct / Decimal('100')

    @inventory_target_base.setter
    def inventory_target_base(self, value: Decimal):
        self.inventory_target_base_pct = value * Decimal('100')

    @property
    def order_optimization_enabled(self) -> bool:
        return self._config_map.order_optimization_enabled

    @property
    def order_refresh_time(self) -> float:
        return self._config_map.order_refresh_time

    @property
    def filled_order_delay(self) -> float:
        return self._config_map.filled_order_delay

    @property
    def order_override(self) -> Dict[str, any]:
        return self._config_map.order_override

    @property
    def order_levels(self) -> int:
        return self._config_map.order_levels

    def get_config_map_execution_mode(self):
        # Simplified implementation
        pass

    def get_config_map_hanging_orders(self):
        # Simplified implementation
        pass

    def c_add_markets(self, markets):
        # Simplified implementation
        self._sb_markets = markets