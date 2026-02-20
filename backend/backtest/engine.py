from typing import List, Dict
from dataclasses import dataclass
import pandas as pd
import numpy as np
from core.logger import logger
from strategies.base import BaseStrategy, SignalType
from data.processors import indicators

@dataclass
class BacktestResult:
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    trades: List[Dict]
    equity_curve: List[float]

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, commission_rate: float = 0.001):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
    
    async def run(self, strategy: BaseStrategy, df: pd.DataFrame, symbol: str = 'BTCUSDT') -> BacktestResult:
        logger.info(f"回测: {strategy.NAME}")
        df = indicators.add_all_indicators(df)
        
        capital = self.initial_capital
        position = None
        trades = []
        equity_curve = [capital]
        
        for i in range(len(df)):
            current_df = df.iloc[:i+1]
            current = df.iloc[i]
            current_price = current['close']
            
            signal = await strategy.generate_signal(current_df, position)
            
            if signal:
                if signal.signal_type == SignalType.BUY and position is None:
                    quantity = capital * 0.95 / current_price
                    cost = quantity * current_price * (1 + self.commission_rate)
                    if cost <= capital:
                        position = {'quantity': quantity, 'entry_price': current_price, 'cost': cost}
                        capital -= cost
                        trades.append({'type': 'BUY', 'price': current_price, 'quantity': quantity, 'time': str(current.name)})
                elif signal.signal_type == SignalType.SELL and position is not None:
                    revenue = position['quantity'] * current_price * (1 - self.commission_rate)
                    pnl = revenue - position['cost']
                    capital += revenue
                    trades.append({'type': 'SELL', 'price': current_price, 'quantity': position['quantity'], 'time': str(current.name), 'pnl': pnl})
                    position = None
            
            equity = capital + position['quantity'] * current_price if position else capital
            equity_curve.append(equity)
        
        return self._calculate_metrics(df, trades, equity_curve)
    
    def _calculate_metrics(self, df: pd.DataFrame, trades: List[Dict], equity_curve: List[float]) -> BacktestResult:
        equity_series = pd.Series(equity_curve)
        returns = equity_series.pct_change().dropna()
        
        total_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital * 100
        days = len(df)
        annual_return = (1 + total_return / 100) ** (365 / days) - 1 if days > 0 else 0
        annual_return *= 100
        
        peak = equity_series.expanding(min_periods=1).max()
        drawdown = (equity_series - peak) / peak
        max_drawdown = drawdown.min() * 100
        
        excess_returns = returns - 0.02 / 365
        sharpe_ratio = np.sqrt(365) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
        
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        winning = len([t for t in sell_trades if t.get('pnl', 0) > 0])
        losing = len([t for t in sell_trades if t.get('pnl', 0) <= 0])
        total = len(sell_trades)
        win_rate = winning / total * 100 if total > 0 else 0
        
        total_profit = sum([t['pnl'] for t in sell_trades if t.get('pnl', 0) > 0])
        total_loss = abs(sum([t['pnl'] for t in sell_trades if t.get('pnl', 0) < 0]))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        return BacktestResult(
            total_return=total_return, annual_return=annual_return, max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio, win_rate=win_rate, profit_factor=profit_factor,
            total_trades=total, winning_trades=winning, losing_trades=losing,
            trades=trades, equity_curve=equity_curve
        )

backtest_engine = BacktestEngine()
