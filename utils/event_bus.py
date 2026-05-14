from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, DefaultDict, Dict, List, Optional
from uuid import uuid4

from loguru import logger


@dataclass
class Event:
    topic: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
    source: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventBus:
    def __init__(self, max_history: int = 1000):
        self._subscribers: DefaultDict[str, List[Callable[[Event], None]]] = defaultdict(list)
        self._history: Deque[Event] = deque(maxlen=max_history)

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        self._subscribers[topic].append(handler)
        logger.debug(f"事件订阅: {topic} -> {getattr(handler, '__name__', handler.__class__.__name__)}")

    def publish(self, topic: str, payload: Dict[str, Any], source: str = "system") -> Event:
        event = Event(topic=topic, payload=payload, source=source)
        self._history.append(event)
        handlers = list(self._subscribers.get(topic, [])) + list(self._subscribers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"事件处理失败 topic={topic}: {e}")
        return event

    def recent(self, topic: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        events = [event for event in self._history if topic is None or event.topic == topic]
        return [event.to_dict() for event in events[-limit:]]


def get_event_bus() -> EventBus:
    global _EVENT_BUS
    try:
        return _EVENT_BUS
    except NameError:
        _EVENT_BUS = EventBus()
        return _EVENT_BUS
