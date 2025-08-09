import asyncio
import time
from decimal import Decimal
from typing import Dict, List, Set, Tuple, TYPE_CHECKING, Union

from hummingbot.client.config.trade_fee_schema_loader import TradeFeeSchemaLoader
from hummingbot.connector.in_flight_order_base import InFlightOrderBase
from hummingbot.connector.utils import split_hb_trading_pair, TradeFillOrderDetails
from hummingbot.connector.constants import s_decimal_NaN, s_decimal_0
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.market_order import MarketOrder
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.network_iterator import NetworkIterator
from hummingbot.core.rate_oracle.rate_oracle import RateOracle
from hummingbot.core.utils.estimate_fee import estimate_fee

if TYPE_CHECKING:
    from hummingbot.client.config.client_config_map import ClientConfigMap
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class ConnectorBase(NetworkIterator):
    MARKET_EVENTS = [
        MarketEvent.ReceivedAsset,
        MarketEvent.BuyOrderCompleted,
        MarketEvent.SellOrderCompleted,
        MarketEvent.WithdrawAsset,
        MarketEvent.OrderCancelled,
        MarketEvent.OrderFilled,
        MarketEvent.OrderExpired,
        MarketEvent.OrderFailure,
        MarketEvent.TransactionFailure,
        MarketEvent.BuyOrderCreated,
        MarketEvent.SellOrderCreated,
        MarketEvent.FundingPaymentCompleted,
        MarketEvent.RangePositionLiquidityAdded,
        MarketEvent.RangePositionLiquidityRemoved,
        MarketEvent.RangePositionUpdate,
        MarketEvent.RangePositionUpdateFailure,
        MarketEvent.RangePositionFeeCollected,
    ]

    def __init__(self, client_config_map: "ClientConfigAdapter"):
        super().__init__()

        self._event_reporter = EventReporter(event_source=self.display_name)
        self._event_logger = EventLogger(event_source=self.display_name)
        for event_tag in self.MARKET_EVENTS:
            self.c_add_listener(event_tag.value, self._event_reporter)
            self.c_add_listener(event_tag.value, self._event_logger)

        self._account_balances = {}  # Dict[asset_name:str, Decimal]
        self._account_available_balances = {}  # Dict[asset_name:str, Decimal]
        # _real_time_balance_update is used to flag whether the connector provides real time balance updates.
        # if not, the available will be calculated based on what happened since snapshot taken.
        self._real_time_balance_update = True
        # If _real_time_balance_update is set to False, Sub classes of this connector class need to set values
        # for _in_flight_orders_snapshot and _in_flight_orders_snapshot_timestamp when the update user balances.
        self._in_flight_orders_snapshot = {}  # Dict[order_id:str, InFlightOrderBase]
        self._in_flight_orders_snapshot_timestamp = 0.0
        self._current_trade_fills = set()
        self._exchange_order_ids = dict()
        self._trade_fee_schema = None
        self._trade_volume_metric_collector = client_config_map.anonymized_metrics_mode.get_collector(
            connector=self,
            rate_provider=RateOracle.get_instance(),
            instance_id=client_config_map.instance_id,
        )
        self._client_config: Union[ClientConfigAdapter, ClientConfigMap] = client_config_map  # for IDE autocomplete

    @property
    def real_time_balance_update(self) -> bool:
        return self._real_time_balance_update

    @real_time_balance_update.setter
    def real_time_balance_update(self, value: bool):
        self._real_time_balance_update = value

    @property
    def in_flight_orders_snapshot(self) -> Dict[str, InFlightOrderBase]:
        return self._in_flight_orders_snapshot

    @in_flight_orders_snapshot.setter
    def in_flight_orders_snapshot(self, value: Dict[str, InFlightOrderBase]):
        self._in_flight_orders_snapshot = value

    @property
    def in_flight_orders_snapshot_timestamp(self) -> float:
        return self._in_flight_orders_snapshot_timestamp

    @in_flight_orders_snapshot_timestamp.setter
    def in_flight_orders_snapshot_timestamp(self, value: float):
        self._in_flight_orders_snapshot_timestamp = value

    def estimate_fee_pct(self, is_maker: bool) -> Decimal:
        """
        Estimate the trading fee for maker or taker type of order
        :param is_maker: Whether to get trading for maker or taker order
        :returns An estimated fee in percentage value
        """
        return estimate_fee(self.name, is_maker).percent

    @staticmethod
    def split_trading_pair(trading_pair: str) -> Tuple[str, str]:
        return split_hb_trading_pair(trading_pair)

    def in_flight_asset_balances(self, in_flight_orders: Dict[str, InFlightOrderBase]) -> Dict[str, Decimal]:
        """
        Calculates total asset balances locked in in_flight_orders including fee (estimated)
        For BUY order, this is the quote asset balance locked in the order
        For SELL order, this is the base asset balance locked in the order
        :param in_flight_orders: a dictionary of in-flight orders
        :return A dictionary of tokens and their balance locked in the orders
        """
        asset_balances = {}
        if in_flight_orders is None:
            return asset_balances
        for order in (o for o in in_flight_orders.values() if not (o.is_done or o.is_failure or o.is_cancelled)):
            outstanding_amount = order.amount - order.executed_amount_base
            if order.trade_type is TradeType.BUY:
                outstanding_value = outstanding_amount * order.price
                if order.quote_asset not in asset_balances:
                    asset_balances[order.quote_asset] = s_decimal_0
                fee = self.estimate_fee_pct(True)
                outstanding_value *= Decimal(1) + fee
                asset_balances[order.quote_asset] += outstanding_value
            else:
                if order.base_asset not in asset_balances:
                    asset_balances[order.base_asset] = s_decimal_0
                asset_balances[order.base_asset] += outstanding_amount
        return asset_balances

    def order_filled_balances(self, starting_timestamp = 0) -> Dict[str, Decimal]:
        """
        Calculates total asset balance changes from filled orders since the timestamp
        For BUY filled order, the quote balance goes down while the base balance goes up, and for SELL order, it's the
        opposite. This does not account for fee.
        :param starting_timestamp: The starting timestamp to include filter order filled events
        :returns A dictionary of tokens and their balance
        """
        order_filled_events = list(filter(lambda e: isinstance(e, OrderFilledEvent), self.event_logs))
        order_filled_events = [o for o in order_filled_events if o.timestamp > starting_timestamp]
        balances = {}
        for event in order_filled_events:
            base, quote = event.trading_pair.split("-")[0], event.trading_pair.split("-")[1]
            if event.trade_type is TradeType.BUY:
                quote_value = Decimal("-1") * event.price * event.amount
                base_value = event.amount
            else:
                quote_value = event.price * event.amount
                base_value = Decimal("-1") * event.amount
            if base not in balances:
                balances[base] = s_decimal_0
            if quote not in balances:
                balances[quote] = s_decimal_0
            balances[base] += base_value
            balances[quote] += quote_value
        return balances

    def get_exchange_limit_config(self, market: str) -> Dict[str, object]:
        """
        Retrieves the Balance Limits for the specified market.
        """
        exchange_limits = self._client_config.balance_asset_limit.get(market, {})
        return exchange_limits if exchange_limits is not None else {}

    @property
    def status_dict(self) -> Dict[str, bool]:
        """
        A dictionary of statuses of various connector's components.
        """
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def event_logs(self) -> List[any]:
        return self._event_logger.event_log

    @property
    def ready(self) -> bool:
        """
        Indicates whether the connector is ready to be used.
        """
        raise NotImplementedError

    @property
    def in_flight_orders(self) -> Dict[str, InFlightOrderBase]:
        raise NotImplementedError


class EventReporter:
    def __init__(self, event_source: str):
        self.event_source = event_source

    def __call__(self, event):
        # Simple event reporter implementation
        pass
