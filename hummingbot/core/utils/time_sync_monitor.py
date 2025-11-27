"""
NTP time synchronization monitor with clock drift detection.
"""
import asyncio
import logging
import socket
import struct
import time
from typing import Optional, Callable

from hummingbot.logger import HummingbotLogger


class TimeSyncMonitor:
    """
    Monitor for NTP time synchronization and clock drift detection.

    Features:
    - NTP time synchronization checking
    - Clock drift detection and monitoring
    - Configurable drift thresholds
    - Trading halt on excessive drift
    """

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self,
                 drift_threshold_ms: float = 1000.0,
                 check_interval: float = 60.0,
                 ntp_servers: Optional[list] = None,
                 on_drift_exceeded: Optional[Callable] = None):
        """
        Initialize time sync monitor.

        Args:
            drift_threshold_ms: Maximum allowed clock drift in milliseconds
            check_interval: Interval between sync checks in seconds
            ntp_servers: List of NTP servers to use
            on_drift_exceeded: Callback when drift threshold is exceeded
        """
        self.drift_threshold_ms = drift_threshold_ms
        self.check_interval = check_interval
        self.on_drift_exceeded = on_drift_exceeded

        self.ntp_servers = ntp_servers or [
            "pool.ntp.org",
            "time.google.com",
            "time.cloudflare.com",
            "time.apple.com"
        ]

        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_drift = 0.0
        self._drift_history = []
        self._max_history = 100

        # Trading state
        self._trading_allowed = True
        self._drift_exceeded_count = 0
        self._max_drift_violations = 3

    async def get_ntp_time(self, server: str, timeout: float = 5.0) -> Optional[float]:
        """
        Get time from NTP server.

        Args:
            server: NTP server hostname
            timeout: Timeout for NTP request

        Returns:
            NTP timestamp or None if failed
        """
        try:
            # NTP packet format (48 bytes)
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(timeout)

            # NTP request packet
            msg = b'\x1b' + 47 * b'\0'

            # Send request
            client.sendto(msg, (server, 123))

            # Receive response
            data, address = client.recvfrom(1024)
            client.close()

            if len(data) >= 48:
                # Extract timestamp from NTP response (seconds since 1900)
                timestamp = struct.unpack('!12I', data)[10]
                # Convert to Unix timestamp (seconds since 1970)
                return timestamp - 2208988800

        except Exception as e:
            self.logger().debug(f"Failed to get NTP time from {server}: {e}")

        return None

    async def get_accurate_time(self) -> Optional[float]:
        """
        Get accurate time from multiple NTP servers.

        Returns:
            Average NTP time or None if all servers failed
        """
        ntp_times = []

        for server in self.ntp_servers:
            ntp_time = await self.get_ntp_time(server)
            if ntp_time is not None:
                ntp_times.append(ntp_time)

        if ntp_times:
            # Return median time to handle outliers
            ntp_times.sort()
            n = len(ntp_times)
            if n % 2 == 0:
                return (ntp_times[n//2 - 1] + ntp_times[n//2]) / 2
            else:
                return ntp_times[n//2]

        return None

    async def measure_drift(self) -> Optional[float]:
        """
        Measure clock drift against NTP time.

        Returns:
            Clock drift in milliseconds (positive = local clock fast)
        """
        local_time = time.time()
        ntp_time = await self.get_accurate_time()

        if ntp_time is None:
            self.logger().warning("Failed to get NTP time from any server")
            return None

        drift_seconds = local_time - ntp_time
        drift_ms = drift_seconds * 1000

        self.logger().debug(f"Clock drift: {drift_ms:.2f}ms")
        return drift_ms

    def _update_drift_history(self, drift: float):
        """Update drift history for trend analysis."""
        self._drift_history.append({
            'timestamp': time.time(),
            'drift_ms': drift
        })

        # Keep only recent history
        if len(self._drift_history) > self._max_history:
            self._drift_history = self._drift_history[-self._max_history:]

    def get_drift_statistics(self) -> dict:
        """Get drift statistics from history."""
        if not self._drift_history:
            return {}

        drifts = [entry['drift_ms'] for entry in self._drift_history]

        return {
            'current_drift_ms': self._last_drift,
            'average_drift_ms': sum(drifts) / len(drifts),
            'max_drift_ms': max(drifts),
            'min_drift_ms': min(drifts),
            'drift_trend': self._calculate_drift_trend(),
            'samples': len(drifts)
        }

    def _calculate_drift_trend(self) -> str:
        """Calculate drift trend from recent history."""
        if len(self._drift_history) < 3:
            return "insufficient_data"

        recent_drifts = [entry['drift_ms'] for entry in self._drift_history[-5:]]

        # Simple trend calculation
        if recent_drifts[-1] > recent_drifts[0] + 10:
            return "increasing"
        elif recent_drifts[-1] < recent_drifts[0] - 10:
            return "decreasing"
        else:
            return "stable"

    async def check_time_sync(self) -> bool:
        """
        Check time synchronization and handle drift violations.

        Returns:
            True if time sync is acceptable, False otherwise
        """
        drift = await self.measure_drift()

        if drift is None:
            self.logger().warning("Unable to measure clock drift - allowing trading")
            return True

        self._last_drift = drift
        self._update_drift_history(drift)

        # Check if drift exceeds threshold
        if abs(drift) > self.drift_threshold_ms:
            self._drift_exceeded_count += 1
            self.logger().warning(
                f"Clock drift {drift:.2f}ms exceeds threshold {self.drift_threshold_ms}ms "
                f"(violation {self._drift_exceeded_count}/{self._max_drift_violations})"
            )

            # Halt trading if too many violations
            if self._drift_exceeded_count >= self._max_drift_violations:
                self._trading_allowed = False
                self.logger().error(
                    f"Clock drift violations exceeded limit - HALTING TRADING. "
                    f"Current drift: {drift:.2f}ms"
                )

                if self.on_drift_exceeded:
                    try:
                        await self.on_drift_exceeded(drift)
                    except Exception as e:
                        self.logger().error(f"Error in drift exceeded callback: {e}")

                return False
        else:
            # Reset violation count on good measurement
            if self._drift_exceeded_count > 0:
                self.logger().info(f"Clock drift back to normal: {drift:.2f}ms")
            self._drift_exceeded_count = 0
            self._trading_allowed = True

        return True

    async def _monitor_loop(self):
        """Main monitoring loop."""
        self.logger().info(
            f"Starting time sync monitoring (threshold: {self.drift_threshold_ms}ms, "
            f"interval: {self.check_interval}s)"
        )

        while self._monitoring:
            try:
                await self.check_time_sync()
            except Exception as e:
                self.logger().error(f"Error in time sync check: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval)

    def start_monitoring(self):
        """Start time synchronization monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self.logger().info("Time sync monitoring started")

    def stop_monitoring(self):
        """Stop time synchronization monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()

        self.logger().info("Time sync monitoring stopped")

    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed based on time sync status."""
        return self._trading_allowed

    @property
    def current_drift_ms(self) -> float:
        """Get current clock drift in milliseconds."""
        return self._last_drift

    def force_allow_trading(self):
        """Force allow trading (use with caution)."""
        self._trading_allowed = True
        self._drift_exceeded_count = 0
        self.logger().warning("Trading forcefully enabled despite time sync issues")