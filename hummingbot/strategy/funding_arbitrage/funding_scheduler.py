"""
Funding settlement scheduler with precise exchange timing and timezone support.
Handles different settlement schedules across exchanges and provides closing windows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from enum import Enum
import pytz
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class SettlementStatus(Enum):
    """Status of funding settlement window."""
    SAFE_TO_OPEN = "safe_to_open"           # Safe to open new positions
    CLOSING_WINDOW = "closing_window"       # Should consider closing soon
    SETTLEMENT_IMMINENT = "settlement_imminent"  # Close positions immediately
    POST_SETTLEMENT = "post_settlement"     # Recently settled, wait for data


@dataclass
class SettlementTime:
    """Represents a funding settlement time."""
    hour: int
    minute: int = 0
    tz: str = 'UTC'
    
    def to_utc_time(self, date: datetime) -> datetime:
        """Convert to UTC datetime for given date."""
        tz = pytz.timezone(self.tz)
        local_time = tz.localize(datetime.combine(date, datetime.min.time().replace(
            hour=self.hour, minute=self.minute
        )))
        return local_time.astimezone(pytz.UTC)


@dataclass
class ExchangeSchedule:
    """Funding schedule configuration for an exchange."""
    exchange_name: str
    settlement_times: List[SettlementTime]  # Times when funding settles
    tz: str = 'UTC'
    pre_settlement_buffer_minutes: int = 5  # Close positions this many minutes before
    post_settlement_delay_minutes: int = 2  # Wait this long after settlement for data
    funding_rate_update_delay_minutes: int = 1  # How long after settlement rates update


class FundingScheduler:
    """
    Manages funding settlement schedules across multiple exchanges.
    Provides timing information for position management decisions.
    """
    
    def __init__(self):
        self.exchange_schedules = self._initialize_exchange_schedules()
        
    def _initialize_exchange_schedules(self) -> Dict[str, ExchangeSchedule]:
        """Initialize known exchange funding schedules."""
        schedules = {}
        
        # Binance: 00:00, 08:00, 16:00 UTC
        schedules['binance'] = ExchangeSchedule(
            exchange_name='binance',
            settlement_times=[
                SettlementTime(0, 0, 'UTC'),
                SettlementTime(8, 0, 'UTC'),
                SettlementTime(16, 0, 'UTC'),
            ],
            pre_settlement_buffer_minutes=3,
            post_settlement_delay_minutes=2,
        )
        
        schedules['binance_perpetual'] = schedules['binance']
        
        # Bybit: 00:00, 08:00, 16:00 UTC  
        schedules['bybit'] = ExchangeSchedule(
            exchange_name='bybit',
            settlement_times=[
                SettlementTime(0, 0, 'UTC'),
                SettlementTime(8, 0, 'UTC'), 
                SettlementTime(16, 0, 'UTC'),
            ],
            pre_settlement_buffer_minutes=5,
            post_settlement_delay_minutes=3,
        )
        
        schedules['bybit_perpetual'] = schedules['bybit']
        
        # OKX: 00:00, 08:00, 16:00 UTC
        schedules['okx'] = ExchangeSchedule(
            exchange_name='okx',
            settlement_times=[
                SettlementTime(0, 0, 'UTC'),
                SettlementTime(8, 0, 'UTC'),
                SettlementTime(16, 0, 'UTC'),
            ],
            pre_settlement_buffer_minutes=4,
            post_settlement_delay_minutes=2,
        )
        
        schedules['okx_perpetual'] = schedules['okx']
        
        # Gate.io: 00:00, 08:00, 16:00 UTC
        schedules['gate_io'] = ExchangeSchedule(
            exchange_name='gate_io',
            settlement_times=[
                SettlementTime(0, 0, 'UTC'),
                SettlementTime(8, 0, 'UTC'),
                SettlementTime(16, 0, 'UTC'),
            ],
            pre_settlement_buffer_minutes=5,
            post_settlement_delay_minutes=3,
        )
        
        schedules['gate_io_perpetual'] = schedules['gate_io']
        
        # KuCoin: 00:00, 08:00, 16:00 UTC
        schedules['kucoin'] = ExchangeSchedule(
            exchange_name='kucoin', 
            settlement_times=[
                SettlementTime(0, 0, 'UTC'),
                SettlementTime(8, 0, 'UTC'),
                SettlementTime(16, 0, 'UTC'),
            ],
            pre_settlement_buffer_minutes=6,
            post_settlement_delay_minutes=3,
        )
        
        schedules['kucoin_perpetual'] = schedules['kucoin']
        
        # Hyperliquid: HOURLY funding (every hour at :00)
        schedules['hyperliquid'] = ExchangeSchedule(
            exchange_name='hyperliquid',
            settlement_times=[
                SettlementTime(hour, 0, 'UTC') for hour in range(24)
            ],
            pre_settlement_buffer_minutes=3,  # Close 3 min before hourly settlement
            post_settlement_delay_minutes=2,
        )

        schedules['hyperliquid_perpetual'] = schedules['hyperliquid']

        return schedules
    
    def get_settlement_status(self, 
                             exchanges: List[str], 
                             current_time: Optional[datetime] = None) -> Tuple[SettlementStatus, Dict[str, int]]:
        """
        Get current settlement status for a list of exchanges.
        
        Args:
            exchanges: List of exchange names to check
            current_time: Current time (UTC), defaults to now
            
        Returns:
            Tuple of (overall status, dict of minutes to next settlement per exchange)
        """
        if current_time is None:
            current_time = datetime.now(pytz.UTC)
        
        if not isinstance(current_time, datetime):
            # Handle timestamp input
            current_time = datetime.fromtimestamp(current_time, tz=pytz.UTC)
        
        minutes_to_settlement = {}
        statuses = []
        
        for exchange in exchanges:
            schedule = self.exchange_schedules.get(exchange.lower())
            if not schedule:
                logger.warning(f"No schedule found for exchange: {exchange}")
                continue
                
            next_settlement, minutes_until = self._get_next_settlement(schedule, current_time)
            minutes_to_settlement[exchange] = minutes_until
            
            # Determine status for this exchange
            if minutes_until <= 0:
                # We're in or past settlement time
                status = SettlementStatus.POST_SETTLEMENT
            elif minutes_until <= schedule.pre_settlement_buffer_minutes:
                status = SettlementStatus.SETTLEMENT_IMMINENT
            elif minutes_until <= schedule.pre_settlement_buffer_minutes + 15:
                status = SettlementStatus.CLOSING_WINDOW
            else:
                status = SettlementStatus.SAFE_TO_OPEN
                
            statuses.append(status)
        
        # Overall status is the most restrictive
        if SettlementStatus.SETTLEMENT_IMMINENT in statuses:
            overall_status = SettlementStatus.SETTLEMENT_IMMINENT
        elif SettlementStatus.POST_SETTLEMENT in statuses:
            overall_status = SettlementStatus.POST_SETTLEMENT
        elif SettlementStatus.CLOSING_WINDOW in statuses:
            overall_status = SettlementStatus.CLOSING_WINDOW
        else:
            overall_status = SettlementStatus.SAFE_TO_OPEN
            
        return overall_status, minutes_to_settlement
    
    def should_open_position(self, 
                           exchanges: List[str], 
                           minimum_time_horizon_minutes: int = 30,
                           current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Determine if it's safe to open a new position.
        
        Args:
            exchanges: Exchanges involved in the arbitrage
            minimum_time_horizon_minutes: Minimum time needed before settlement
            current_time: Current time (UTC)
            
        Returns:
            Tuple of (should_open, reason)
        """
        status, minutes_to_settlement = self.get_settlement_status(exchanges, current_time)
        
        if status == SettlementStatus.SETTLEMENT_IMMINENT:
            return False, "Settlement imminent on one or more exchanges"
        
        if status == SettlementStatus.POST_SETTLEMENT:
            return False, "Recently settled, waiting for fresh funding rate data"
        
        # Check if we have enough time horizon
        min_time_remaining = min(minutes_to_settlement.values()) if minutes_to_settlement else 0
        if min_time_remaining < minimum_time_horizon_minutes:
            return False, f"Insufficient time horizon: {min_time_remaining} min < {minimum_time_horizon_minutes} min required"
        
        return True, f"Safe to open, {min_time_remaining} minutes until next settlement"
    
    def should_close_position(self, 
                            exchanges: List[str],
                            position_age_minutes: float,
                            min_hold_time_minutes: int = 10,
                            current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Determine if positions should be closed due to settlement timing.
        
        Args:
            exchanges: Exchanges with open positions
            position_age_minutes: How long positions have been open
            min_hold_time_minutes: Minimum time to hold position
            current_time: Current time (UTC)
            
        Returns:
            Tuple of (should_close, reason)
        """
        status, minutes_to_settlement = self.get_settlement_status(exchanges, current_time)
        
        # Always close if settlement is imminent
        if status == SettlementStatus.SETTLEMENT_IMMINENT:
            return True, "Settlement imminent - closing all positions"
        
        # Check if position has been held long enough
        if position_age_minutes < min_hold_time_minutes:
            return False, f"Position too young: {position_age_minutes:.1f} min < {min_hold_time_minutes} min minimum"
        
        # Consider closing in closing window if position is mature
        if status == SettlementStatus.CLOSING_WINDOW:
            min_time_remaining = min(minutes_to_settlement.values()) if minutes_to_settlement else 0
            return True, f"Entering settlement window - {min_time_remaining} minutes remaining"
        
        return False, "No timing-based reason to close"
    
    def _get_next_settlement(self, 
                           schedule: ExchangeSchedule, 
                           current_time: datetime) -> Tuple[datetime, int]:
        """
        Get next settlement time for an exchange.
        
        Returns:
            Tuple of (next_settlement_datetime, minutes_until_settlement)
        """
        current_date = current_time.date()
        
        # Check settlements for today
        today_settlements = []
        for settlement_time in schedule.settlement_times:
            settlement_datetime = settlement_time.to_utc_time(current_date)
            today_settlements.append(settlement_datetime)
        
        # Find next settlement today
        for settlement in sorted(today_settlements):
            if settlement > current_time:
                minutes_until = int((settlement - current_time).total_seconds() / 60)
                return settlement, minutes_until
        
        # No more settlements today, check tomorrow
        tomorrow = current_date + timedelta(days=1)
        tomorrow_settlements = []
        for settlement_time in schedule.settlement_times:
            settlement_datetime = settlement_time.to_utc_time(tomorrow)
            tomorrow_settlements.append(settlement_datetime)
        
        next_settlement = min(tomorrow_settlements)
        minutes_until = int((next_settlement - current_time).total_seconds() / 60)
        
        return next_settlement, minutes_until
    
    def get_funding_window_info(self, 
                               exchanges: List[str],
                               current_time: Optional[datetime] = None) -> Dict[str, Dict]:
        """
        Get detailed funding window information for all exchanges.
        
        Returns:
            Dict with detailed timing info per exchange
        """
        if current_time is None:
            current_time = datetime.now(pytz.UTC)
            
        info = {}
        
        for exchange in exchanges:
            schedule = self.exchange_schedules.get(exchange.lower())
            if not schedule:
                continue
                
            next_settlement, minutes_until = self._get_next_settlement(schedule, current_time)
            
            info[exchange] = {
                'next_settlement_utc': next_settlement,
                'minutes_until_settlement': minutes_until,
                'pre_settlement_buffer': schedule.pre_settlement_buffer_minutes,
                'post_settlement_delay': schedule.post_settlement_delay_minutes,
                'safe_open_window_ends': next_settlement - timedelta(
                    minutes=schedule.pre_settlement_buffer_minutes + 15
                ),
                'close_window_starts': next_settlement - timedelta(
                    minutes=schedule.pre_settlement_buffer_minutes + 15
                ),
                'must_close_by': next_settlement - timedelta(
                    minutes=schedule.pre_settlement_buffer_minutes
                ),
            }
        
        return info
    
    def add_custom_schedule(self, exchange_name: str, schedule: ExchangeSchedule):
        """Add custom settlement schedule for an exchange."""
        self.exchange_schedules[exchange_name.lower()] = schedule
        logger.info(f"Added custom schedule for {exchange_name}")
    
    def get_next_safe_opening_window(self, 
                                   exchanges: List[str],
                                   current_time: Optional[datetime] = None) -> Tuple[datetime, int]:
        """
        Get the next time window safe for opening positions.
        
        Returns:
            Tuple of (window_start_time, duration_minutes)
        """
        if current_time is None:
            current_time = datetime.now(pytz.UTC)
        
        # Get all settlements for next 24 hours
        all_settlements = []
        for exchange in exchanges:
            schedule = self.exchange_schedules.get(exchange.lower())
            if not schedule:
                continue
                
            # Get settlements for today and tomorrow
            for days_ahead in [0, 1]:
                check_date = current_time.date() + timedelta(days=days_ahead)
                for settlement_time in schedule.settlement_times:
                    settlement_dt = settlement_time.to_utc_time(check_date)
                    if settlement_dt > current_time:
                        buffer_start = settlement_dt - timedelta(
                            minutes=schedule.pre_settlement_buffer_minutes + 15
                        )
                        buffer_end = settlement_dt + timedelta(
                            minutes=schedule.post_settlement_delay_minutes
                        )
                        all_settlements.append((buffer_start, buffer_end))
        
        all_settlements.sort()
        
        # Find gaps between settlements
        if not all_settlements:
            return current_time, 60  # Default 1 hour window
        
        # Check if we're currently in a safe window
        now_safe = True
        for start, end in all_settlements:
            if start <= current_time <= end:
                now_safe = False
                break
        
        if now_safe:
            # Find how long current window lasts
            future_starts = [start for start, _ in all_settlements if start > current_time]
            if not future_starts:
                # No more settlements in near future, use large window
                return current_time, 480  # 8 hours default

            next_restriction = min(future_starts)
            duration = int((next_restriction - current_time).total_seconds() / 60)
            return current_time, duration
        
        # Find next safe window
        for i, (_, end) in enumerate(all_settlements):
            if end <= current_time:
                continue
            
            window_start = max(end, current_time)
            
            # Find when this window ends
            if i + 1 < len(all_settlements):
                next_start, _ = all_settlements[i + 1]
                duration = int((next_start - window_start).total_seconds() / 60)
            else:
                duration = 480  # 8 hours default
                
            return window_start, duration
        
        # Fallback
        return current_time + timedelta(hours=1), 480