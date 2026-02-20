import pandas as pd
from typing import Optional, Dict
from datetime import datetime
from strategies.base import BaseStrategy, Signal, SignalType
from core.logger import logger

class ConvergenceBreakoutStrategy(BaseStrategy):
    NAME = "convergence_breakout"
    VERSION = "3.0.0"
    DESCRIPTION = "收敛突破趋势策略"
    
    DEFAULT_PARAMS = {
        'lookback': 20,
        'stop_loss_percent': 2.0,
        'take_profit_ratio': 2.0,
        'volume_multiplier': 1.5,
    }
    
    def __init__(self, params: Optional[Dict] = None):
        super().__init__(params)
        self.lookback = self.params['lookback']
        self.stop_loss_percent = self.params['stop_loss_percent']
        self.take_profit_ratio = self.params['take_profit_ratio']
        self.volume_multiplier = self.params['volume_multiplier']
        self._entry_price = 0.0
    
    async def generate_signal(self, df: pd.DataFrame, position: Optional[Dict] = None) -> Optional[Signal]:
        if len(df) < self.lookback + 10: return None
        
        current = df.iloc[-1]
        current_price = current['close']
        symbol = 'BTCUSDT'
        has_position = position is not None and position.get('quantity', 0) > 0
        
        if has_position:
            entry_price = position.get('entryPrice', self._entry_price)
            quantity = position.get('quantity', 0)
            if entry_price > 0:
                pnl_percent = (current_price - entry_price) / entry_price * 100
                if pnl_percent <= -self.stop_loss_percent:
                    return Signal(strategy_name=self.NAME, signal_type=SignalType.SELL, symbol=symbol,
                                 price=current_price, quantity=quantity, confidence=1.0)
                if pnl_percent >= self.stop_loss_percent * self.take_profit_ratio:
                    return Signal(strategy_name=self.NAME, signal_type=SignalType.SELL, symbol=symbol,
                                 price=current_price, quantity=quantity, confidence=1.0)
        
        if not has_position:
            is_converging = self._detect_convergence(df)
            is_breakout_up = self._detect_breakout_up(df)
            volume_ma = current.get('volume_ma', current['volume'])
            volume_confirmed = current['volume'] > volume_ma * self.volume_multiplier
            rsi_ok = current.get('rsi', 50) < 70
            
            if is_converging and is_breakout_up and volume_confirmed and rsi_ok:
                self._entry_price = current_price
                return Signal(
                    strategy_name=self.NAME, signal_type=SignalType.BUY, symbol=symbol,
                    price=current_price, confidence=0.8,
                    stop_loss=current_price * (1 - self.stop_loss_percent / 100),
                    take_profit=current_price * (1 + self.stop_loss_percent * self.take_profit_ratio / 100)
                )
        return None
    
    def _detect_convergence(self, df: pd.DataFrame) -> bool:
        if len(df) < self.lookback * 2: return False
        recent = df.tail(self.lookback)
        prev = df.iloc[-self.lookback * 2:-self.lookback]
        return recent['close'].pct_change().std() < prev['close'].pct_change().std()
    
    def _detect_breakout_up(self, df: pd.DataFrame) -> bool:
        if len(df) < self.lookback + 1: return False
        current = df.iloc[-1]
        prev_high = df.iloc[-self.lookback - 1:-1]['high'].max()
        return current['close'] > prev_high and current['close'] > current['open']
