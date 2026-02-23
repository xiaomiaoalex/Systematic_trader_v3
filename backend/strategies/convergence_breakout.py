import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime

from core.logger import logger
# 👇 删除了无用的 config 导入
from strategies.base import BaseStrategy, Signal, SignalType

class ConvergenceBreakoutStrategy(BaseStrategy):
    """
    极速向量化版：三角收敛突破策略
    - 核心逻辑：通道极度收缩后，价格向上突破，且伴随巨量。趋势破位后止损/止盈。
    - 特性：完全向量化、无 for 循环、参数解耦适配前端 UI。
    """
    
    NAME = "convergence_breakout"
    DESCRIPTION = "三角收敛突破策略"
    VERSION = "1.0.0"
    DEFAULT_PARAMS = {
        "convergence_window": 20,
        "squeeze_threshold": 0.02,
        "volume_window": 5,
        "volume_multiplier": 1.5,
        "trend_ma_period": 20
    }

    @classmethod
    def get_ui_schema(cls) -> list:
        return [
            {"name": "convergence_window", "label": "收敛观察周期(K线数)", "type": "number", "default": 20},
            {"name": "squeeze_threshold", "label": "收敛极限阈值(%)", "type": "number", "default": 0.02},
            {"name": "volume_window", "label": "量能对比周期", "type": "number", "default": 5},
            {"name": "volume_multiplier", "label": "爆发放量倍数", "type": "number", "default": 1.5},
            {"name": "trend_ma_period", "label": "趋势护航/止损周期", "type": "number", "default": 20},
        ]

    async def generate_signal(self, df: pd.DataFrame, position: Optional[Dict] = None) -> Optional[Signal]:
        if df.empty or len(df) < max(self.params["convergence_window"], self.params["trend_ma_period"]):
            return None

        p = self.params

        # 1. 计算支撑与阻力位 (前 N 根 K 线的最高/最低)
        df['rolling_high'] = df['high'].rolling(window=p['convergence_window']).max().shift(1)
        df['rolling_low'] = df['low'].rolling(window=p['convergence_window']).min().shift(1)

        # 2. 收敛度量 (通道压缩)
        df['channel_width'] = (df['rolling_high'] - df['rolling_low']) / df['close']
        df['is_converged'] = df['channel_width'] <= p['squeeze_threshold']

        # 3. 计算突破前 5 根 K 线的平均成交量
        df['pre_avg_vol'] = df['volume'].rolling(window=p['volume_window']).mean().shift(1)

        # 4. 计算趋势基准线 (EMA均线)
        df['trend_ma'] = df['close'].ewm(span=p['trend_ma_period'], adjust=False).mean()

        latest = df.iloc[-1]
        
        # 👇 核心修复：直接从 DataFrame 中提取当前交易对名称，如果没传就默认兜底
        current_symbol = str(latest.get('symbol', 'BTCUSDT'))
        
        current_position = 0.0
        if position:
            current_position = float(position.get('quantity', 0.0))
        
        is_breakout_up = (
            latest['is_converged'] and 
            (latest['close'] > latest['rolling_high']) and 
            (latest['volume'] >= latest['pre_avg_vol'] * p['volume_multiplier'])
        )

        is_trend_broken = latest['close'] < latest['trend_ma']

        if current_position <= 0.0:  
            if is_breakout_up:
                logger.info(f"🚀 [三角收敛突破] 触发！价格: {latest['close']}, 突破量能: {latest['volume']:.2f} (前均量: {latest['pre_avg_vol']:.2f})")
                return Signal(
                    strategy_name=self.NAME,
                    signal_type=SignalType.BUY,
                    symbol=current_symbol,  # 👈 修复点：彻底摆脱对全局单数 config 的依赖
                    price=float(latest['close']),
                    quantity=0.0,
                    confidence=0.8,
                    metadata={'reason': 'Convergence Breakout & Volume Surge'}
                )
                
        elif current_position > 0.0:  
            if is_trend_broken:
                logger.info(f"🛡️ [趋势破位] 离场信号触发！当前价格 {latest['close']} 跌破均线 {latest['trend_ma']:.2f}")
                return Signal(
                    strategy_name=self.NAME,
                    signal_type=SignalType.SELL,
                    symbol=current_symbol,  # 👈 修复点
                    price=float(latest['close']),
                    quantity=current_position,
                    confidence=0.9,
                    metadata={'reason': 'Trend Breakdown (Stop Loss/Take Profit)'}
                )

        return None