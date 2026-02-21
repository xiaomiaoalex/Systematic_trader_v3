import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime

from core.logger import logger
from core.config import config
from strategies.base import BaseStrategy, Signal, SignalType

class ConvergenceBreakoutStrategy(BaseStrategy):
    """
    极速向量化版：三角收敛突破策略
    - 核心逻辑：通道极度收缩后，价格向上突破，且伴随巨量。趋势破位后止损/止盈。
    - 特性：完全向量化、无 for 循环、参数解耦适配前端 UI。
    """
    
    # 策略全局唯一标识
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
        """
        【适配需求 4：前后端解耦】
        前端 UI 只需要调用这个接口，就能自动渲染出带有中文名称的参数调整表单。
        """
        return [
            {"name": "convergence_window", "label": "收敛观察周期(K线数)", "type": "number", "default": 20},
            {"name": "squeeze_threshold", "label": "收敛极限阈值(%)", "type": "number", "default": 0.02},
            {"name": "volume_window", "label": "量能对比周期", "type": "number", "default": 5},
            {"name": "volume_multiplier", "label": "爆发放量倍数", "type": "number", "default": 1.5},
            {"name": "trend_ma_period", "label": "趋势护航/止损周期", "type": "number", "default": 20},
        ]

    async def generate_signal(self, df: pd.DataFrame, position: Optional[Dict] = None) -> Optional[Signal]:
        """
        核心分析引擎：接收 Pandas DataFrame 和 当前持仓状态，返回标准解耦信号。
        【适配需求 3：标的和执行解耦】这里只负责算信号，不碰交易所 API，不区分现货合约。
        """
        # 数据量不够时不产生信号
        if df.empty or len(df) < max(self.params["convergence_window"], self.params["trend_ma_period"]):
            return None

        p = self.params

        # ==========================================
        # ⚡ 向量化引擎开始 (毫秒级计算) ⚡
        # ==========================================
        
        # 1. 计算支撑与阻力位 (前 N 根 K 线的最高/最低)
        # 注意：必须用 .shift(1) 把当前K线排除在外，避免"未来函数"作弊！
        df['rolling_high'] = df['high'].rolling(window=p['convergence_window']).max().shift(1)
        df['rolling_low'] = df['low'].rolling(window=p['convergence_window']).min().shift(1)

        # 2. 收敛度量 (通道压缩)
        # 用价格带的宽度 / 现价，如果非常小，说明进入了三角收敛末端
        df['channel_width'] = (df['rolling_high'] - df['rolling_low']) / df['close']
        df['is_converged'] = df['channel_width'] <= p['squeeze_threshold']

        # 3. 【适配需求 2：成交量过滤】计算突破前 5 根 K 线的平均成交量
        # 同样必须 .shift(1)，计算"真正的突破前均量"
        df['pre_avg_vol'] = df['volume'].rolling(window=p['volume_window']).mean().shift(1)

        # 4. 【适配需求 1：趋势破位止损】计算趋势基准线 (EMA均线)
        df['trend_ma'] = df['close'].ewm(span=p['trend_ma_period'], adjust=False).mean()

        # ==========================================
        # 🎯 提取最新状态，生成决策
        # ==========================================
        latest = df.iloc[-1]
        
        # 获取当前持仓
        current_position = 0.0
        if position:
            current_position = float(position.get('quantity', 0.0))
        
        # 做多突破条件：之前处于收敛态 AND 现价突破阻力位 AND 成交量达标
        is_breakout_up = (
            latest['is_converged'] and 
            (latest['close'] > latest['rolling_high']) and 
            (latest['volume'] >= latest['pre_avg_vol'] * p['volume_multiplier'])
        )

        # 趋势破位离场条件：收盘价跌破护航均线
        is_trend_broken = latest['close'] < latest['trend_ma']

        # 状态机机制：根据当前是否持有仓位，下达解耦指令
        if current_position <= 0.0:  # 空仓状态，寻找入场机会
            if is_breakout_up:
                logger.info(f"🚀 [三角收敛突破] 触发！价格: {latest['close']}, 突破量能: {latest['volume']:.2f} (前均量: {latest['pre_avg_vol']:.2f})")
                return Signal(
                    strategy_name=self.NAME,
                    signal_type=SignalType.BUY,
                    symbol=config.trading.symbol,
                    price=float(latest['close']),
                    quantity=0.0,
                    confidence=0.8,
                    metadata={'reason': 'Convergence Breakout & Volume Surge'}
                )
                
        elif current_position > 0.0:  # 持仓状态，盯紧止损/止盈线
            if is_trend_broken:
                logger.info(f"🛡️ [趋势破位] 离场信号触发！当前价格 {latest['close']} 跌破均线 {latest['trend_ma']:.2f}")
                return Signal(
                    strategy_name=self.NAME,
                    signal_type=SignalType.SELL,
                    symbol=config.trading.symbol,
                    price=float(latest['close']),
                    quantity=current_position,
                    confidence=0.9,
                    metadata={'reason': 'Trend Breakdown (Stop Loss/Take Profit)'}
                )

        # 默认不动
        return None