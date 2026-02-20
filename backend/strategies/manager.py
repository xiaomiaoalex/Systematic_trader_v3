from typing import Optional, List, Dict, Type
import pandas as pd
from strategies.base import BaseStrategy, Signal
from core.logger import logger

class StrategyManager:
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
        self._strategy_classes: Dict[str, Type[BaseStrategy]] = {}
    
    def register_strategy(self, strategy_class: Type[BaseStrategy], params: Optional[Dict] = None) -> BaseStrategy:
        strategy = strategy_class(params)
        self._strategies[strategy.NAME] = strategy
        self._strategy_classes[strategy.NAME] = strategy_class
        logger.info(f"策略已注册: {strategy.NAME}")
        return strategy
    
    def enable_strategy(self, name: str, params: Optional[Dict] = None) -> bool:
        if name in self._strategies:
            self._strategies[name].enable()
            return True
        if name in self._strategy_classes:
            self.register_strategy(self._strategy_classes[name], params)
            return True
        return False
    
    def disable_strategy(self, name: str) -> bool:
        if name in self._strategies:
            self._strategies[name].disable()
            return True
        return False
    
    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        return self._strategies.get(name)
    
    def get_enabled_strategies(self) -> List[BaseStrategy]:
        return [s for s in self._strategies.values() if s.is_enabled]
    
    async def generate_signals(self, df: pd.DataFrame, position: Optional[Dict] = None) -> List[Signal]:
        signals = []
        for strategy in self.get_enabled_strategies():
            try:
                signal = await strategy.generate_signal(df, position)
                if signal and strategy.validate_signal(signal):
                    signals.append(signal)
                    strategy.update_stats(signal)
            except Exception as e:
                logger.error(f"策略 {strategy.NAME} 错误: {e}")
        return signals

strategy_manager = StrategyManager()
