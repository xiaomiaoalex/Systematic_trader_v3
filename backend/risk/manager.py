from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from core.config import config
from core.logger import logger
from core.database import db

@dataclass
class RiskStatus:
    daily_pnl: float = 0.0
    daily_loss_percent: float = 0.0
    current_drawdown: float = 0.0
    risk_level: str = "low"
    can_trade: bool = True

class PositionManager:
    def __init__(self):
        self.symbol = config.trading.symbol
        self.max_position_percent = config.trading.max_position_percent
        self._balance: float = 0.0
        self._available_balance: float = 0.0
    
    async def update_balance(self, balance: float, available: float) -> None:
        self._balance = balance
        self._available_balance = available
    
    def calculate_position_size(self, price: float, leverage: int = 1) -> float:
        if price <= 0: return 0.0
        available = self._available_balance or self._balance
        return round(available * (self.max_position_percent / 100) / price, 6)
    
    async def get_position(self, symbol: Optional[str] = None) -> Optional[Dict]:
        open_trades = await db.get_open_trades(symbol or self.symbol)
        if open_trades:
            t = open_trades[0]
            return {'symbol': t['symbol'], 'quantity': t['quantity'], 'entryPrice': t['entry_price']}
        return None
    
    @property
    def balance(self) -> float:
        return self._balance

class RiskManager:
    def __init__(self):
        self.max_daily_loss_percent = config.trading.max_daily_loss_percent
        self.max_drawdown_percent = config.trading.max_drawdown_percent
        self._daily_pnl: float = 0.0
        self._daily_start_balance: float = 0.0
        self._peak_balance: float = 0.0
        self._current_drawdown: float = 0.0
    
    async def initialize(self, initial_balance: float) -> None:
        self._daily_start_balance = initial_balance
        self._peak_balance = initial_balance
        logger.info(f"风险管理初始化: {initial_balance}")
    
    async def check_pre_trade(self, symbol: str, side: str, quantity: float, price: float, leverage: int = 1) -> Tuple[bool, str]:
        if self._daily_pnl < 0:
            daily_loss = abs(self._daily_pnl) / self._daily_start_balance * 100
            if daily_loss >= self.max_daily_loss_percent:
                return False, f"日亏损限制: {daily_loss:.2f}%"
        if self._current_drawdown >= self.max_drawdown_percent:
            return False, f"最大回撤: {self._current_drawdown:.2f}%"
        return True, "OK"
    
    def update_balance(self, current_balance: float) -> None:
        if current_balance > self._peak_balance:
            self._peak_balance = current_balance
        if self._peak_balance > 0:
            self._current_drawdown = (self._peak_balance - current_balance) / self._peak_balance * 100
    
    def get_risk_status(self) -> RiskStatus:
        # 👇 ====== 余额字典解析补丁 ====== 👇
        start_balance = self._daily_start_balance
        # 如果余额是个字典，就精准提取 USDT 的总额
        if isinstance(start_balance, dict):
            start_balance = float(start_balance.get('total', {}).get('USDT', 0.0))
        else:
            start_balance = float(start_balance)
            
        # 安全计算每日回撤
        pnl = float(self._daily_pnl) if isinstance(self._daily_pnl, (int, float)) else 0.0
        daily_loss = (abs(pnl) / start_balance * 100) if start_balance > 0 else 0.0
        # 👆 ============================== 👆
        risk_level = "low"
        can_trade = True
        if daily_loss >= self.max_daily_loss_percent * 0.8 or self._current_drawdown >= self.max_drawdown_percent * 0.8:
            risk_level = "high"
            can_trade = False
        return RiskStatus(daily_pnl=self._daily_pnl, daily_loss_percent=daily_loss,
                         current_drawdown=self._current_drawdown, risk_level=risk_level, can_trade=can_trade)

position_manager = PositionManager()
risk_manager = RiskManager()
