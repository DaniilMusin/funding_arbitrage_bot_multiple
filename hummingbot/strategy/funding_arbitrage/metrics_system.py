"""
Metrics collection and monitoring system for funding arbitrage strategy.
Provides comprehensive metrics tracking, alerting, and export capabilities.
"""

import time
import json
import logging
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected."""
    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution of values


@dataclass
class MetricValue:
    """A single metric value with timestamp."""
    value: Decimal
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """Time series of metric values."""
    name: str
    metric_type: MetricType
    description: str
    values: deque = field(default_factory=lambda: deque(maxlen=1000))  # Keep last 1000 points

    def add(self, value: Decimal, labels: Optional[Dict[str, str]] = None):
        """Add a new value to the series."""
        self.values.append(MetricValue(
            value=value,
            timestamp=time.time(),
            labels=labels or {}
        ))

    def get_latest(self) -> Optional[MetricValue]:
        """Get the latest value."""
        return self.values[-1] if self.values else None

    def get_sum(self, since: Optional[float] = None) -> Decimal:
        """Get sum of values since timestamp."""
        if since is None:
            return sum(v.value for v in self.values)
        return sum(v.value for v in self.values if v.timestamp >= since)

    def get_average(self, since: Optional[float] = None) -> Decimal:
        """Get average of values since timestamp."""
        relevant_values = [v for v in self.values if since is None or v.timestamp >= since]
        if not relevant_values:
            return Decimal("0")
        return sum(v.value for v in relevant_values) / Decimal(len(relevant_values))


class MetricsCollector:
    """
    Collects and manages all strategy metrics.
    Provides aggregation, alerting, and export capabilities.
    """

    def __init__(self, enable_file_export: bool = True, export_interval: int = 60):
        self.metrics: Dict[str, MetricSeries] = {}
        self.enable_file_export = enable_file_export
        self.export_interval = export_interval
        self.last_export_time = time.time()

        # Alert thresholds
        self.alert_thresholds: Dict[str, Dict[str, Decimal]] = {}
        self.alert_callbacks: List = []

        # Initialize core metrics
        self._initialize_core_metrics()

    def _initialize_core_metrics(self):
        """Initialize all core strategy metrics."""

        # Opportunity metrics
        self.register_metric(
            "opportunities_scanned_total",
            MetricType.COUNTER,
            "Total number of opportunities scanned"
        )
        self.register_metric(
            "opportunities_profitable_total",
            MetricType.COUNTER,
            "Total number of profitable opportunities found"
        )
        self.register_metric(
            "opportunities_executed_total",
            MetricType.COUNTER,
            "Total number of opportunities executed"
        )
        self.register_metric(
            "opportunities_skipped_total",
            MetricType.COUNTER,
            "Total number of opportunities skipped"
        )
        self.register_metric(
            "opportunities_failed_total",
            MetricType.COUNTER,
            "Total number of failed executions"
        )

        # Position metrics
        self.register_metric(
            "positions_active",
            MetricType.GAUGE,
            "Number of currently active positions"
        )
        self.register_metric(
            "positions_total_notional",
            MetricType.GAUGE,
            "Total notional value of active positions"
        )

        # PnL metrics
        self.register_metric(
            "pnl_realized_total",
            MetricType.COUNTER,
            "Total realized PnL"
        )
        self.register_metric(
            "pnl_unrealized_current",
            MetricType.GAUGE,
            "Current unrealized PnL"
        )
        self.register_metric(
            "funding_collected_total",
            MetricType.COUNTER,
            "Total funding payments collected"
        )

        # Risk metrics
        self.register_metric(
            "margin_utilization",
            MetricType.GAUGE,
            "Current margin utilization percentage"
        )
        self.register_metric(
            "leverage_current",
            MetricType.GAUGE,
            "Current average leverage"
        )
        self.register_metric(
            "hedge_gap_max",
            MetricType.GAUGE,
            "Maximum hedge gap percentage"
        )

        # Margin status metrics
        for status in ["healthy", "warning", "danger", "critical", "liquidation_risk"]:
            self.register_metric(
                f"margin_status_{status}_count",
                MetricType.GAUGE,
                f"Number of positions in {status} margin status"
            )

        # Performance metrics
        self.register_metric(
            "edge_calculation_avg",
            MetricType.GAUGE,
            "Average edge of executed opportunities"
        )
        self.register_metric(
            "slippage_realized_avg",
            MetricType.GAUGE,
            "Average realized slippage"
        )
        self.register_metric(
            "execution_time_ms",
            MetricType.HISTOGRAM,
            "Execution time in milliseconds"
        )

        # Error metrics
        self.register_metric(
            "errors_api_total",
            MetricType.COUNTER,
            "Total API errors"
        )
        self.register_metric(
            "errors_order_total",
            MetricType.COUNTER,
            "Total order placement errors"
        )
        self.register_metric(
            "errors_critical_total",
            MetricType.COUNTER,
            "Total critical errors"
        )

    def register_metric(self, name: str, metric_type: MetricType, description: str):
        """Register a new metric."""
        if name not in self.metrics:
            self.metrics[name] = MetricSeries(
                name=name,
                metric_type=metric_type,
                description=description
            )
            logger.debug(f"Registered metric: {name}")

    def increment(self, name: str, value: Decimal = Decimal("1"), labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        if name not in self.metrics:
            logger.warning(f"Metric {name} not registered, ignoring increment")
            return

        current = self.metrics[name].get_latest()
        new_value = (current.value if current else Decimal("0")) + value
        self.metrics[name].add(new_value, labels)

    def set_gauge(self, name: str, value: Decimal, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric value."""
        if name not in self.metrics:
            logger.warning(f"Metric {name} not registered, ignoring set")
            return

        self.metrics[name].add(value, labels)

    def record_histogram(self, name: str, value: Decimal, labels: Optional[Dict[str, str]] = None):
        """Record a histogram value."""
        if name not in self.metrics:
            logger.warning(f"Metric {name} not registered, ignoring record")
            return

        self.metrics[name].add(value, labels)

    def set_alert_threshold(self, metric_name: str, condition: str, threshold: Decimal):
        """
        Set an alert threshold for a metric.

        Args:
            metric_name: Name of the metric
            condition: Condition type ('gt', 'lt', 'eq', 'gte', 'lte')
            threshold: Threshold value
        """
        if metric_name not in self.alert_thresholds:
            self.alert_thresholds[metric_name] = {}

        self.alert_thresholds[metric_name][condition] = threshold
        logger.info(f"Set alert threshold for {metric_name}: {condition} {threshold}")

    def register_alert_callback(self, callback):
        """Register a callback for alerts."""
        self.alert_callbacks.append(callback)

    def check_alerts(self):
        """Check all metrics against alert thresholds."""
        for metric_name, thresholds in self.alert_thresholds.items():
            if metric_name not in self.metrics:
                continue

            latest = self.metrics[metric_name].get_latest()
            if not latest:
                continue

            for condition, threshold in thresholds.items():
                triggered = False

                if condition == 'gt' and latest.value > threshold:
                    triggered = True
                elif condition == 'lt' and latest.value < threshold:
                    triggered = True
                elif condition == 'gte' and latest.value >= threshold:
                    triggered = True
                elif condition == 'lte' and latest.value <= threshold:
                    triggered = True
                elif condition == 'eq' and latest.value == threshold:
                    triggered = True

                if triggered:
                    alert = {
                        'metric': metric_name,
                        'value': float(latest.value),
                        'condition': condition,
                        'threshold': float(threshold),
                        'timestamp': latest.timestamp
                    }

                    logger.warning(f"Alert triggered: {metric_name} {condition} {threshold} (value: {latest.value})")

                    for callback in self.alert_callbacks:
                        try:
                            callback(alert)
                        except Exception as e:
                            logger.error(f"Error in alert callback: {e}")

    def get_snapshot(self) -> Dict[str, Any]:
        """Get a snapshot of all current metrics."""
        snapshot = {
            'timestamp': time.time(),
            'metrics': {}
        }

        for name, series in self.metrics.items():
            latest = series.get_latest()
            if latest:
                snapshot['metrics'][name] = {
                    'value': float(latest.value),
                    'timestamp': latest.timestamp,
                    'type': series.metric_type.value,
                    'description': series.description,
                    'labels': latest.labels
                }

        return snapshot

    def get_summary(self, window_seconds: int = 3600) -> Dict[str, Any]:
        """
        Get a summary of metrics over a time window.

        Args:
            window_seconds: Time window in seconds (default 1 hour)
        """
        cutoff_time = time.time() - window_seconds
        summary = {
            'window_seconds': window_seconds,
            'timestamp': time.time(),
            'metrics': {}
        }

        for name, series in self.metrics.items():
            if series.metric_type == MetricType.COUNTER:
                summary['metrics'][name] = {
                    'total': float(series.get_sum(cutoff_time)),
                    'type': 'counter'
                }
            elif series.metric_type == MetricType.GAUGE:
                latest = series.get_latest()
                summary['metrics'][name] = {
                    'current': float(latest.value) if latest else 0.0,
                    'average': float(series.get_average(cutoff_time)),
                    'type': 'gauge'
                }
            elif series.metric_type == MetricType.HISTOGRAM:
                values = [v.value for v in series.values if v.timestamp >= cutoff_time]
                if values:
                    summary['metrics'][name] = {
                        'count': len(values),
                        'average': float(sum(values) / len(values)),
                        'min': float(min(values)),
                        'max': float(max(values)),
                        'type': 'histogram'
                    }

        return summary

    def export_to_file(self, filepath: str):
        """Export metrics snapshot to JSON file."""
        try:
            snapshot = self.get_snapshot()
            with open(filepath, 'w') as f:
                json.dump(snapshot, f, indent=2)
            logger.debug(f"Exported metrics to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export metrics to file: {e}")

    def should_export(self) -> bool:
        """Check if it's time to export metrics."""
        return time.time() - self.last_export_time >= self.export_interval

    def periodic_export(self, base_filepath: str):
        """Perform periodic export if enabled and due."""
        if not self.enable_file_export:
            return

        if self.should_export():
            timestamp = int(time.time())
            filepath = f"{base_filepath}_metrics_{timestamp}.json"
            self.export_to_file(filepath)
            self.last_export_time = time.time()

    def get_dashboard_summary(self) -> str:
        """Get a human-readable dashboard summary."""
        snapshot = self.get_snapshot()
        metrics = snapshot.get('metrics', {})

        lines = []
        lines.append("=" * 60)
        lines.append("FUNDING ARBITRAGE BOT - METRICS DASHBOARD")
        lines.append("=" * 60)
        lines.append("")

        # Opportunities section
        lines.append("📊 OPPORTUNITIES")
        lines.append(f"  Scanned:     {metrics.get('opportunities_scanned_total', {}).get('value', 0):.0f}")
        lines.append(f"  Profitable:  {metrics.get('opportunities_profitable_total', {}).get('value', 0):.0f}")
        lines.append(f"  Executed:    {metrics.get('opportunities_executed_total', {}).get('value', 0):.0f}")
        lines.append(f"  Skipped:     {metrics.get('opportunities_skipped_total', {}).get('value', 0):.0f}")
        lines.append(f"  Failed:      {metrics.get('opportunities_failed_total', {}).get('value', 0):.0f}")
        lines.append("")

        # Positions section
        lines.append("📈 POSITIONS")
        lines.append(f"  Active:      {metrics.get('positions_active', {}).get('value', 0):.0f}")
        lines.append(f"  Total Notional: ${metrics.get('positions_total_notional', {}).get('value', 0):,.2f}")
        lines.append("")

        # PnL section
        lines.append("💰 PnL")
        lines.append(f"  Realized:    ${metrics.get('pnl_realized_total', {}).get('value', 0):,.2f}")
        lines.append(f"  Unrealized:  ${metrics.get('pnl_unrealized_current', {}).get('value', 0):,.2f}")
        lines.append(f"  Funding:     ${metrics.get('funding_collected_total', {}).get('value', 0):,.2f}")
        lines.append("")

        # Risk section
        lines.append("⚠️  RISK")
        lines.append(f"  Margin Util: {metrics.get('margin_utilization', {}).get('value', 0):.1f}%")
        lines.append(f"  Avg Leverage: {metrics.get('leverage_current', {}).get('value', 0):.2f}x")
        lines.append(f"  Max Hedge Gap: {metrics.get('hedge_gap_max', {}).get('value', 0):.2f}%")
        lines.append("")

        # Errors section
        lines.append("❌ ERRORS")
        lines.append(f"  API Errors:  {metrics.get('errors_api_total', {}).get('value', 0):.0f}")
        lines.append(f"  Order Errors: {metrics.get('errors_order_total', {}).get('value', 0):.0f}")
        lines.append(f"  Critical:    {metrics.get('errors_critical_total', {}).get('value', 0):.0f}")
        lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)
