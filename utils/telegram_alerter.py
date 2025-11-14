"""
Telegram Alerter for Funding Arbitrage Bot
Sends critical alerts to Telegram for monitoring
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime
from enum import Enum


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "ℹ️ INFO"
    WARNING = "⚠️ WARNING"
    CRITICAL = "🚨 CRITICAL"
    SUCCESS = "✅ SUCCESS"


class TelegramAlerter:
    """
    Sends alerts to Telegram for critical bot events.

    Setup:
    1. Create bot via @BotFather on Telegram
    2. Get bot token
    3. Get your chat_id (send message to bot, then check via API)
    4. Set environment variables:
       - TELEGRAM_BOT_TOKEN
       - TELEGRAM_CHAT_ID
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram alerter.

        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Chat ID to send alerts to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logging.getLogger(__name__)
        self.enabled = bool(bot_token and chat_id)

        if not self.enabled:
            self.logger.warning("Telegram alerting disabled: bot_token or chat_id not provided")
        else:
            self.logger.info(f"Telegram alerting enabled for chat_id: {chat_id}")

    def _format_message(self, level: AlertLevel, title: str, message: str, details: Optional[dict] = None) -> str:
        """Format alert message with consistent structure"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg = f"{level.value} **{title}**\n\n"
        msg += f"🕐 Time: `{timestamp}`\n"
        msg += f"📝 Message: {message}\n"

        if details:
            msg += "\n📊 Details:\n"
            for key, value in details.items():
                msg += f"  • {key}: `{value}`\n"

        return msg

    async def _send_async(self, message: str):
        """Send message asynchronously via Telegram Bot API"""
        if not self.enabled:
            self.logger.debug(f"Alert (disabled): {message}")
            return

        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        self.logger.debug("Telegram alert sent successfully")
                    else:
                        self.logger.error(f"Failed to send Telegram alert: {response.status}")
        except ImportError:
            self.logger.error("aiohttp not installed. Install with: pip install aiohttp")
        except Exception as e:
            self.logger.error(f"Error sending Telegram alert: {e}")

    def _send_sync(self, message: str):
        """Send message synchronously (fallback for sync contexts)"""
        if not self.enabled:
            self.logger.debug(f"Alert (disabled): {message}")
            return

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.debug("Telegram alert sent successfully")
            else:
                self.logger.error(f"Failed to send Telegram alert: {response.status_code}")
        except ImportError:
            self.logger.error("requests not installed. Install with: pip install requests")
        except Exception as e:
            self.logger.error(f"Error sending Telegram alert: {e}")

    def send(self, level: AlertLevel, title: str, message: str, details: Optional[dict] = None):
        """
        Send alert synchronously.

        Args:
            level: Alert severity level
            title: Alert title
            message: Alert message
            details: Optional dict with additional details
        """
        formatted_msg = self._format_message(level, title, message, details)
        self._send_sync(formatted_msg)

    async def send_async(self, level: AlertLevel, title: str, message: str, details: Optional[dict] = None):
        """
        Send alert asynchronously.

        Args:
            level: Alert severity level
            title: Alert title
            message: Alert message
            details: Optional dict with additional details
        """
        formatted_msg = self._format_message(level, title, message, details)
        await self._send_async(formatted_msg)

    # Convenience methods for different alert levels

    def critical(self, title: str, message: str, details: Optional[dict] = None):
        """Send critical alert (requires immediate attention)"""
        self.send(AlertLevel.CRITICAL, title, message, details)

    def warning(self, title: str, message: str, details: Optional[dict] = None):
        """Send warning alert (needs attention)"""
        self.send(AlertLevel.WARNING, title, message, details)

    def info(self, title: str, message: str, details: Optional[dict] = None):
        """Send info alert (informational)"""
        self.send(AlertLevel.INFO, title, message, details)

    def success(self, title: str, message: str, details: Optional[dict] = None):
        """Send success alert (positive event)"""
        self.send(AlertLevel.SUCCESS, title, message, details)

    # Specific alert methods for bot events

    def alert_emergency_close(self, token: str, reason: str, details: dict):
        """Alert when emergency close is triggered"""
        self.critical(
            title="EMERGENCY CLOSE",
            message=f"Position for {token} closed due to: {reason}",
            details=details
        )

    def alert_position_opened(self, token: str, connector_1: str, connector_2: str, position_size: float):
        """Alert when new position is opened"""
        self.info(
            title="Position Opened",
            message=f"New arbitrage position opened for {token}",
            details={
                "Token": token,
                "Exchange 1": connector_1,
                "Exchange 2": connector_2,
                "Position Size": f"${position_size:.2f}"
            }
        )

    def alert_position_closed(self, token: str, pnl: float, reason: str):
        """Alert when position is closed"""
        level = AlertLevel.SUCCESS if pnl > 0 else AlertLevel.WARNING
        self.send(
            level=level,
            title="Position Closed",
            message=f"Position for {token} closed: {reason}",
            details={
                "Token": token,
                "PnL": f"${pnl:.2f}",
                "Reason": reason
            }
        )

    def alert_high_error_rate(self, error_count: int, time_period: str):
        """Alert when error rate is high"""
        self.warning(
            title="High Error Rate",
            message=f"{error_count} errors in {time_period}",
            details={
                "Error Count": error_count,
                "Time Period": time_period,
                "Action": "Check logs for details"
            }
        )

    def alert_exchange_down(self, exchange: str):
        """Alert when exchange is unavailable"""
        self.warning(
            title="Exchange Down",
            message=f"{exchange} is unavailable",
            details={
                "Exchange": exchange,
                "Status": "Unavailable",
                "Action": "Bot will skip this exchange until recovery"
            }
        )

    def alert_low_balance(self, exchange: str, balance: float, threshold: float):
        """Alert when balance is low"""
        self.warning(
            title="Low Balance Warning",
            message=f"Balance on {exchange} is below threshold",
            details={
                "Exchange": exchange,
                "Current Balance": f"${balance:.2f}",
                "Threshold": f"${threshold:.2f}",
                "Action": "Consider adding funds"
            }
        )

    def alert_bot_started(self, config: dict):
        """Alert when bot starts"""
        self.success(
            title="Bot Started",
            message="Funding arbitrage bot started successfully",
            details=config
        )

    def alert_bot_stopped(self, reason: str):
        """Alert when bot stops"""
        self.critical(
            title="Bot Stopped",
            message=f"Bot stopped: {reason}",
            details={"Reason": reason, "Action": "Check logs and restart"}
        )


# Example usage and testing
if __name__ == "__main__":
    import os

    # Get credentials from environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    # Create alerter
    alerter = TelegramAlerter(bot_token, chat_id)

    # Test alerts
    print("Testing Telegram alerting...")

    # Test 1: Bot started
    alerter.alert_bot_started({
        "Exchanges": "OKX, Hyperliquid",
        "Tokens": "221 tokens",
        "Min Spread": "0.15%"
    })

    # Test 2: Position opened
    alerter.alert_position_opened("BTC", "okx_perpetual", "hyperliquid_perpetual", 10000)

    # Test 3: Warning
    alerter.alert_low_balance("okx_perpetual", 150, 200)

    # Test 4: Critical
    alerter.alert_emergency_close(
        "BTC",
        "Position imbalance 25% > 10%",
        {
            "OKX Notional": "$10,000",
            "Hyperliquid Notional": "$7,500",
            "Imbalance": "25%"
        }
    )

    print("✅ Test alerts sent! Check your Telegram.")
