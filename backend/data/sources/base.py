from dataclasses import dataclass
from datetime import datetime
from typing import Dict

@dataclass
class Kline:
    symbol: str
    interval: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime
    quote_volume: float = 0.0
    trades: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Kline':
        return cls(
            symbol=data['symbol'], interval=data['interval'],
            open_time=datetime.fromisoformat(data['open_time']) if isinstance(data['open_time'], str) else data['open_time'],
            open=float(data['open']), high=float(data['high']), low=float(data['low']),
            close=float(data['close']), volume=float(data['volume']),
            close_time=datetime.fromisoformat(data['close_time']) if isinstance(data['close_time'], str) else data['close_time']
        )
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol, 'interval': self.interval,
            'open_time': self.open_time.isoformat(), 'open': self.open,
            'high': self.high, 'low': self.low, 'close': self.close,
            'volume': self.volume, 'close_time': self.close_time.isoformat()
        }

@dataclass
class Ticker:
    symbol: str
    last: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    timestamp: datetime = None
