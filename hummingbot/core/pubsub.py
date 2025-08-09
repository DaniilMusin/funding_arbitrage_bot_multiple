from enum import Enum
import logging
import random
import weakref
from typing import List, Dict, Set, Any

from hummingbot.logger import HummingbotLogger
from hummingbot.core.event.event_listener import EventListener

class_logger = None


class PubSub:
    """
    PubSub with weak references. This avoids the lapsed listener problem by periodically performing GC on dead
    event listener.
    """

    ADD_LISTENER_GC_PROBABILITY = 0.005

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global class_logger
        if class_logger is None:
            class_logger = logging.getLogger(__name__)
        return class_logger

    def __init__(self):
        self._events: Dict[int, Set[weakref.ref]] = {}

    def add_listener(self, event_tag: Enum, listener: EventListener):
        self.c_add_listener(event_tag.value, listener)

    def remove_listener(self, event_tag: Enum, listener: EventListener):
        self.c_remove_listener(event_tag.value, listener)

    def get_listeners(self, event_tag: Enum) -> List[EventListener]:
        return self.c_get_listeners(event_tag.value)

    def trigger_event(self, event_tag: Enum, message: Any):
        self.c_trigger_event(event_tag.value, message)

    def c_log_exception(self, event_tag: int, arg: Any):
        self.logger().error(f"Unexpected error while processing event {event_tag}.", exc_info=True)

    def c_add_listener(self, event_tag: int, listener: EventListener):
        if event_tag not in self._events:
            self._events[event_tag] = set()

        listener_weakref = weakref.ref(listener)
        self._events[event_tag].add(listener_weakref)

        if random.random() < PubSub.ADD_LISTENER_GC_PROBABILITY:
            self.c_remove_dead_listeners(event_tag)

    def c_remove_listener(self, event_tag: int, listener: EventListener):
        if event_tag not in self._events:
            return

        # Find and remove the weakref for this listener
        to_remove = None
        for weakref_listener in self._events[event_tag]:
            if weakref_listener() == listener:
                to_remove = weakref_listener
                break

        if to_remove:
            self._events[event_tag].discard(to_remove)

        self.c_remove_dead_listeners(event_tag)

    def c_remove_dead_listeners(self, event_tag: int):
        if event_tag not in self._events:
            return

        # Remove dead listeners
        dead_refs = set()
        for weakref_listener in self._events[event_tag]:
            if weakref_listener() is None:
                dead_refs.add(weakref_listener)

        for dead_ref in dead_refs:
            self._events[event_tag].discard(dead_ref)

        # Remove empty event entries
        if not self._events[event_tag]:
            del self._events[event_tag]

    def c_get_listeners(self, event_tag: int) -> List[EventListener]:
        self.c_remove_dead_listeners(event_tag)

        if event_tag not in self._events:
            return []

        retval = []
        for weakref_listener in self._events[event_tag]:
            listener = weakref_listener()
            if listener is not None:
                retval.append(listener)
        return retval

    def c_trigger_event(self, event_tag: int, arg: Any):
        self.c_remove_dead_listeners(event_tag)

        if event_tag not in self._events:
            return

        # Create a copy to avoid modification during iteration
        listeners_copy = list(self._events[event_tag])

        for weakref_listener in listeners_copy:
            listener = weakref_listener()
            if listener is not None:
                try:
                    listener.c_set_event_info(event_tag, self)
                    listener.c_call(arg)
                except Exception:
                    self.c_log_exception(event_tag, arg)
                finally:
                    listener.c_set_event_info(0, None)
