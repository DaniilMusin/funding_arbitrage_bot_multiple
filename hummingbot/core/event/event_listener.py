from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from hummingbot.core.pubsub import PubSub


class EventListener:
    def __init__(self):
        self._current_event_tag = 0
        self._current_event_caller = None

    def __call__(self, arg: Any):
        raise NotImplementedError

    @property
    def current_event_tag(self) -> int:
        return self._current_event_tag

    @property
    def current_event_caller(self) -> 'PubSub':
        return self._current_event_caller

    def c_set_event_info(self, current_event_tag: int, current_event_caller: 'PubSub'):
        self._current_event_tag = current_event_tag
        self._current_event_caller = current_event_caller

    def c_call(self, arg: Any):
        self(arg)