from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hummingbot.core.clock import Clock

from hummingbot.core.pubsub import PubSub

NaN = float("nan")


class TimeIterator(PubSub):
    def __init__(self):
        super().__init__()
        self._current_timestamp = NaN
        self._clock = None

    def c_start(self, clock: 'Clock', timestamp: float):
        self._clock = clock
        self._current_timestamp = timestamp

    def c_stop(self, clock: 'Clock'):
        self._current_timestamp = NaN
        self._clock = None

    def c_tick(self, timestamp: float):
        self._current_timestamp = timestamp

    def tick(self, timestamp: float):
        self.c_tick(timestamp)

    @property
    def current_timestamp(self) -> float:
        return self._current_timestamp

    @property
    def clock(self) -> Optional['Clock']:
        return self._clock

    def start(self, clock: 'Clock'):
        self.c_start(clock, clock.current_timestamp)

    def stop(self, clock: 'Clock'):
        self.c_stop(clock)

    def _set_current_timestamp(self, timestamp: float):
        """
        Method added to be used only for unit testing purposes
        """
        self._current_timestamp = timestamp
