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
        # 原代码：
        # days = len(df)
        
        # 👇 修改为基于真实时间差计算天数 👇
        if len(df) > 1:
            time_diff = df.index[-1] - df.index[0]
            days = time_diff.total_seconds() / (24 * 3600)
        else:
            days = 0
            
        annual_return = (1 + total_return / 100) ** (365 / days) - 1 if days > 0 else 0
        annual_return *= 100
        annual_return = (1 + total_return / 100) ** (365 / days) - 1 if days > 0 else 0
        annual_return *= 100
        
        peak = equity_series.expanding(min_periods=1).max()
        drawdown = (equity_series - peak) / peak
        max_drawdown = drawdown.min() * 100
        
        excess_returns = returns - 0.02 / 365
        
        # 🚨 核心修复 1：夏普比率浮点数陷阱保护
        std_dev = excess_returns.std()
        if std_dev > 1e-6: # 只有波动率大于 0.000001 时才计算夏普
            sharpe_ratio = np.sqrt(365) * excess_returns.mean() / std_dev
        else:
            sharpe_ratio = 0.0
        
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        winning = len([t for t in sell_trades if t.get('pnl', 0) > 0])
        losing = len([t for t in sell_trades if t.get('pnl', 0) <= 0])
        total = len(sell_trades)
        win_rate = winning / total * 100 if total > 0 else 0
        
        total_profit = sum([t['pnl'] for t in sell_trades if t.get('pnl', 0) > 0])
        total_loss = abs(sum([t['pnl'] for t in sell_trades if t.get('pnl', 0) < 0]))
        
        # 🚨 核心修复 2：盈亏比的 0/0 过滤
        if total_loss > 0:
            profit_factor = total_profit / total_loss
        elif total_profit > 0:
            profit_factor = float('inf') # 只有真的赚了钱且没亏损，才是真正的印钞机无穷大
        else:
            profit_factor = 0.0 # 没赚钱也没亏钱，盈亏比就是0
        
        return BacktestResult(
            total_return=total_return, annual_return=annual_return, max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio, win_rate=win_rate, profit_factor=profit_factor,
            total_trades=total, winning_trades=winning, losing_trades=losing,
            trades=trades, equity_curve=equity_curve
        )

backtest_engine = BacktestEngine()
