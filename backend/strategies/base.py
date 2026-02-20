from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import pandas as pd
from core.logger import logger

class SignalType(Enum):
    NONE = 0
    LONG = 1
    SHORT = 2
    CLOSE_LONG = 3
    CLOSE_SHORT = 4
    BUY = 5
    SELL = 6

@dataclass
class Signal:
    strategy_name: str
    signal_type: SignalType
    symbol: str
    price: float
    quantity: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class BaseStrategy(ABC):
    NAME: str = "base_strategy"
    DESCRIPTION: str = "基础策略"
    VERSION: str = "1.0.0"
    DEFAULT_PARAMS: Dict[str, Any] = {}
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._enabled = True
        self._signal_count = 0
        self._win_count = 0
        self._loss_count = 0
        logger.info(f"策略初始化: {self.NAME}")
    
    def enable(self) -> None:
        self._enabled = True
    
    def disable(self) -> None:
        self._enabled = False
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @abstractmethod
    async def generate_signal(self, df: pd.DataFrame, position: Optional[Dict] = None) -> Optional[Signal]:
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        return signal and signal.signal_type != SignalType.NONE
    
    def update_stats(self, signal: Signal, pnl: Optional[float] = None) -> None:
        if signal:
            self._signal_count += 1
            if pnl is not None:
                if pnl >= 0: self._win_count += 1
                else: self._loss_count += 1
    
    def get_stats(self) -> Dict:
        total = self._win_count + self._loss_count
        return {
            'name': self.NAME, 'enabled': self._enabled,
            'signal_count': self._signal_count,
            'win_rate': self._win_count / total * 100 if total > 0 else 0
        }
    
    def update_params(self, params: Dict[str, Any]) -> None:
        self.params.update(params)
