import asyncio
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from core.logger import logger

class EventType(Enum):
    SYSTEM_START = auto()
    SYSTEM_STOP = auto()
    KLINE_UPDATE = auto()
    SIGNAL_GENERATED = auto()
    ORDER_FILLED = auto()
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    # 👇 新增下面这两个
    ADD_SYMBOL = auto()     
    REMOVE_SYMBOL = auto()

@dataclass
class Event:
    event_type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""

class EventBus:
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
    
    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def publish(self, event: Event) -> None:
        asyncio.create_task(self._event_queue.put(event))
    
    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                if event.event_type in self._subscribers:
                    for callback in self._subscribers[event.event_type]:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(event)
                            else:
                                callback(event)
                        except Exception as e:
                            logger.error(f"事件回调错误: {e}")
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        self._running = False

event_bus = EventBus()
