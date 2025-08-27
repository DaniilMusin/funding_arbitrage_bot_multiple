"""
Alerting system with rate limiting and deduplication for Sentry, Slack, and Telegram.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Set, Any, List
from enum import Enum

import requests
import sentry_sdk
from sentry_sdk import capture_exception, capture_message

from hummingbot.logger.observability_logger import get_observability_logger


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertChannel(Enum):
    """Alert delivery channels."""
    SENTRY = "sentry"
    SLACK = "slack"
    TELEGRAM = "telegram"


@dataclass
class Alert:
    """Alert data structure."""
    title: str
    message: str
    severity: AlertSeverity
    component: str
    exchange: Optional[str] = None
    trading_pair: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return asdict(self)
    
    def get_dedup_key(self) -> str:
        """Generate deduplication key for this alert."""
        # Create a consistent key based on title, component, and key metadata
        key_data = {
            "title": self.title,
            "component": self.component,
            "exchange": self.exchange,
            "error_type": self.error_type
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    max_alerts_per_minute: int = 5
    max_alerts_per_hour: int = 20
    max_alerts_per_day: int = 100
    dedup_window_seconds: int = 3600  # 1 hour
    
    # Severity-based rate limits
    critical_max_per_minute: int = 10
    high_max_per_minute: int = 5
    medium_max_per_minute: int = 3
    low_max_per_minute: int = 1


class AlertRateLimiter:
    """Rate limiter for alerts with deduplication."""
    
    def __init__(self, config: RateLimitConfig = None):
        """Initialize rate limiter."""
        self.config = config or RateLimitConfig()
        self.logger = get_observability_logger(__name__)
        
        # Rate limiting counters
        self.minute_counter = {}
        self.hour_counter = {}
        self.day_counter = {}
        
        # Deduplication tracking
        self.seen_alerts: Dict[str, float] = {}  # dedup_key -> timestamp
        
        # Time windows
        self.current_minute = int(time.time() // 60)
        self.current_hour = int(time.time() // 3600)
        self.current_day = int(time.time() // 86400)
    
    def should_send_alert(self, alert: Alert) -> bool:
        """Check if alert should be sent based on rate limits and deduplication."""
        now = time.time()
        
        # Clean up old entries
        self._cleanup_old_entries(now)
        
        # Check deduplication
        dedup_key = alert.get_dedup_key()
        if dedup_key in self.seen_alerts:
            last_seen = self.seen_alerts[dedup_key]
            if now - last_seen < self.config.dedup_window_seconds:
                self.logger.debug_structured(
                    "Alert deduplicated",
                    dedup_key=dedup_key,
                    time_since_last=now - last_seen
                )
                return False
        
        # Check rate limits
        if not self._check_rate_limits(alert.severity):
            self.logger.warning_structured(
                "Alert rate limited",
                severity=alert.severity.value,
                component=alert.component
            )
            return False
        
        # Record the alert
        self.seen_alerts[dedup_key] = now
        self._increment_counters(alert.severity)
        
        return True
    
    def _cleanup_old_entries(self, now: float):
        """Clean up old deduplication entries."""
        cutoff = now - self.config.dedup_window_seconds
        self.seen_alerts = {
            key: timestamp for key, timestamp in self.seen_alerts.items()
            if timestamp > cutoff
        }
        
        # Reset counters if time windows have changed
        current_minute = int(now // 60)
        current_hour = int(now // 3600)
        current_day = int(now // 86400)
        
        if current_minute != self.current_minute:
            self.minute_counter.clear()
            self.current_minute = current_minute
        
        if current_hour != self.current_hour:
            self.hour_counter.clear()
            self.current_hour = current_hour
        
        if current_day != self.current_day:
            self.day_counter.clear()
            self.current_day = current_day
    
    def _check_rate_limits(self, severity: AlertSeverity) -> bool:
        """Check if rate limits are exceeded."""
        # Global rate limits
        if self.minute_counter.get('total', 0) >= self.config.max_alerts_per_minute:
            return False
        if self.hour_counter.get('total', 0) >= self.config.max_alerts_per_hour:
            return False
        if self.day_counter.get('total', 0) >= self.config.max_alerts_per_day:
            return False
        
        # Severity-specific rate limits
        severity_limits = {
            AlertSeverity.CRITICAL: self.config.critical_max_per_minute,
            AlertSeverity.HIGH: self.config.high_max_per_minute,
            AlertSeverity.MEDIUM: self.config.medium_max_per_minute,
            AlertSeverity.LOW: self.config.low_max_per_minute,
            AlertSeverity.INFO: self.config.low_max_per_minute,
        }
        
        severity_key = severity.value
        if self.minute_counter.get(severity_key, 0) >= severity_limits.get(severity, 1):
            return False
        
        return True
    
    def _increment_counters(self, severity: AlertSeverity):
        """Increment rate limit counters."""
        self.minute_counter['total'] = self.minute_counter.get('total', 0) + 1
        self.hour_counter['total'] = self.hour_counter.get('total', 0) + 1
        self.day_counter['total'] = self.day_counter.get('total', 0) + 1
        
        severity_key = severity.value
        self.minute_counter[severity_key] = self.minute_counter.get(severity_key, 0) + 1
        self.hour_counter[severity_key] = self.hour_counter.get(severity_key, 0) + 1
        self.day_counter[severity_key] = self.day_counter.get(severity_key, 0) + 1


class SentryAlerter:
    """Sentry alerting integration."""
    
    def __init__(self, dsn: Optional[str] = None):
        """Initialize Sentry alerter."""
        self.dsn = dsn or os.getenv('SENTRY_DSN')
        self.logger = get_observability_logger(__name__)
        
        if self.dsn:
            sentry_sdk.init(
                dsn=self.dsn,
                traces_sample_rate=0.1,
                environment=os.getenv('ENVIRONMENT', 'production')
            )
            self.enabled = True
        else:
            self.enabled = False
            self.logger.warning_structured("Sentry DSN not configured, Sentry alerts disabled")
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send alert to Sentry."""
        if not self.enabled:
            return False
        
        try:
            # Set context
            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("component", alert.component)
                scope.set_tag("severity", alert.severity.value)
                
                if alert.exchange:
                    scope.set_tag("exchange", alert.exchange)
                if alert.trading_pair:
                    scope.set_tag("trading_pair", alert.trading_pair)
                if alert.error_type:
                    scope.set_tag("error_type", alert.error_type)
                
                if alert.metadata:
                    for key, value in alert.metadata.items():
                        scope.set_extra(key, value)
                
                # Send to Sentry
                if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
                    capture_message(f"{alert.title}: {alert.message}", level='error')
                else:
                    capture_message(f"{alert.title}: {alert.message}", level='warning')
            
            return True
            
        except Exception as e:
            self.logger.error_structured(
                "Failed to send Sentry alert",
                error=str(e),
                alert_title=alert.title
            )
            return False


class SlackAlerter:
    """Slack alerting integration."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Slack alerter."""
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        self.logger = get_observability_logger(__name__)
        self.enabled = bool(self.webhook_url)
        
        if not self.enabled:
            self.logger.warning_structured("Slack webhook URL not configured, Slack alerts disabled")
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send alert to Slack."""
        if not self.enabled:
            return False
        
        try:
            # Color mapping for severity
            colors = {
                AlertSeverity.CRITICAL: "#FF0000",
                AlertSeverity.HIGH: "#FF8800",
                AlertSeverity.MEDIUM: "#FFCC00",
                AlertSeverity.LOW: "#00CCFF",
                AlertSeverity.INFO: "#00FF00",
            }
            
            # Build Slack message
            fields = [
                {
                    "title": "Component",
                    "value": alert.component,
                    "short": True
                },
                {
                    "title": "Severity",
                    "value": alert.severity.value.upper(),
                    "short": True
                }
            ]
            
            if alert.exchange:
                fields.append({
                    "title": "Exchange",
                    "value": alert.exchange,
                    "short": True
                })
            
            if alert.trading_pair:
                fields.append({
                    "title": "Trading Pair",
                    "value": alert.trading_pair,
                    "short": True
                })
            
            payload = {
                "attachments": [{
                    "color": colors.get(alert.severity, "#CCCCCC"),
                    "title": alert.title,
                    "text": alert.message,
                    "fields": fields,
                    "ts": int(time.time())
                }]
            }
            
            # Send to Slack
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            return True
            
        except Exception as e:
            self.logger.error_structured(
                "Failed to send Slack alert",
                error=str(e),
                alert_title=alert.title
            )
            return False


class TelegramAlerter:
    """Telegram alerting integration."""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """Initialize Telegram alerter."""
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.logger = get_observability_logger(__name__)
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            self.logger.warning_structured("Telegram bot token or chat ID not configured, Telegram alerts disabled")
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send alert to Telegram."""
        if not self.enabled:
            return False
        
        try:
            # Severity emojis
            emojis = {
                AlertSeverity.CRITICAL: "🚨",
                AlertSeverity.HIGH: "⚠️",
                AlertSeverity.MEDIUM: "🔶",
                AlertSeverity.LOW: "🔵",
                AlertSeverity.INFO: "ℹ️",
            }
            
            # Build message
            emoji = emojis.get(alert.severity, "📋")
            message_lines = [
                f"{emoji} *{alert.title}*",
                "",
                alert.message,
                "",
                f"*Component:* {alert.component}",
                f"*Severity:* {alert.severity.value.upper()}"
            ]
            
            if alert.exchange:
                message_lines.append(f"*Exchange:* {alert.exchange}")
            
            if alert.trading_pair:
                message_lines.append(f"*Trading Pair:* {alert.trading_pair}")
            
            if alert.error_type:
                message_lines.append(f"*Error Type:* {alert.error_type}")
            
            message = "\n".join(message_lines)
            
            # Send to Telegram
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            return True
            
        except Exception as e:
            self.logger.error_structured(
                "Failed to send Telegram alert",
                error=str(e),
                alert_title=alert.title
            )
            return False


class AlertManager:
    """Central alert management with rate limiting and multi-channel delivery."""
    
    def __init__(self, rate_limit_config: RateLimitConfig = None):
        """Initialize alert manager."""
        self.rate_limiter = AlertRateLimiter(rate_limit_config)
        self.logger = get_observability_logger(__name__)
        
        # Initialize alerters
        self.sentry = SentryAlerter()
        self.slack = SlackAlerter()
        self.telegram = TelegramAlerter()
        
        # Channel configuration
        self.channels = {
            AlertChannel.SENTRY: self.sentry,
            AlertChannel.SLACK: self.slack,
            AlertChannel.TELEGRAM: self.telegram,
        }
        
        # Severity-based channel mapping
        self.severity_channels = {
            AlertSeverity.CRITICAL: [AlertChannel.SENTRY, AlertChannel.SLACK, AlertChannel.TELEGRAM],
            AlertSeverity.HIGH: [AlertChannel.SENTRY, AlertChannel.SLACK],
            AlertSeverity.MEDIUM: [AlertChannel.SENTRY],
            AlertSeverity.LOW: [AlertChannel.SENTRY],
            AlertSeverity.INFO: [],  # Info alerts only logged
        }
    
    async def send_alert(self, alert: Alert, channels: Optional[List[AlertChannel]] = None) -> Dict[AlertChannel, bool]:
        """Send alert through specified or default channels."""
        results = {}
        
        # Check rate limits and deduplication
        if not self.rate_limiter.should_send_alert(alert):
            self.logger.debug_structured(
                "Alert suppressed by rate limiter",
                alert_title=alert.title,
                component=alert.component
            )
            return results
        
        # Determine channels to use
        if channels is None:
            channels = self.severity_channels.get(alert.severity, [])
        
        # Log the alert
        self.logger.info_structured(
            "Sending alert",
            alert_title=alert.title,
            severity=alert.severity.value,
            component=alert.component,
            channels=[c.value for c in channels]
        )
        
        # Send to each channel
        for channel in channels:
            alerter = self.channels.get(channel)
            if alerter and alerter.enabled:
                try:
                    success = await alerter.send_alert(alert)
                    results[channel] = success
                except Exception as e:
                    self.logger.error_structured(
                        "Failed to send alert through channel",
                        channel=channel.value,
                        error=str(e),
                        alert_title=alert.title
                    )
                    results[channel] = False
            else:
                results[channel] = False
        
        return results
    
    def create_alert(self, 
                    title: str,
                    message: str,
                    severity: AlertSeverity,
                    component: str,
                    **kwargs) -> Alert:
        """Create an alert with the provided parameters."""
        return Alert(
            title=title,
            message=message,
            severity=severity,
            component=component,
            **kwargs
        )


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


async def send_alert(title: str,
                    message: str,
                    severity: AlertSeverity,
                    component: str,
                    **kwargs) -> Dict[AlertChannel, bool]:
    """Convenience function to send an alert."""
    alert_manager = get_alert_manager()
    alert = alert_manager.create_alert(title, message, severity, component, **kwargs)
    return await alert_manager.send_alert(alert)