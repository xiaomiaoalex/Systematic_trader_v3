from typing import Optional, Dict, Tuple, List
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
        # 💥 拆除单品种枷锁：删除了 self.symbol = config.trading.symbol
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
    
    async def get_position(self, symbol: str) -> Optional[Dict]:
        # 强制要求传入具体的 symbol 进行查询
        open_trades = await db.get_open_trades(symbol)
        if open_trades:
            t = open_trades[0]
            return {'symbol': t['symbol'], 'quantity': t['quantity'], 'entryPrice': t['entry_price']}
        return None

    async def get_all_active_positions(self) -> List[str]:
        """获取当前所有有持仓的品种列表（用于并发风控）"""
        active_symbols = []
        for sym in config.trading.symbols:
            pos = await self.get_position(sym)
            if pos and float(pos.get('quantity', 0.0)) > 0:
                active_symbols.append(sym)
        return active_symbols
    
    @property
    def balance(self) -> float:
        return self._balance

class RiskManager:
    def __init__(self):
        self.max_daily_loss_percent = config.trading.max_daily_loss_percent
        self.max_drawdown_percent = config.trading.max_drawdown_percent
        # 动态获取并发上限，默认最多同时持有3个品种
        self.max_active_trades = getattr(config.trading, 'max_active_trades', 3) 
        self._daily_pnl: float = 0.0
        self._daily_start_balance: float = 0.0
        self._peak_balance: float = 0.0
        self._current_drawdown: float = 0.0
    
    async def initialize(self, initial_balance: float) -> None:
        self._daily_start_balance = initial_balance
        self._peak_balance = initial_balance
        logger.info(f"风险管理初始化: {initial_balance:.2f} USDT | 并发上限: {self.max_active_trades} 个品种")
    
    async def check_pre_trade(self, symbol: str, side: str, quantity: float, price: float, leverage: int = 1) -> Tuple[bool, str]:
        # 1. 资金回撤防线
        if self._daily_pnl < 0:
            daily_loss = abs(self._daily_pnl) / self._daily_start_balance * 100
            if daily_loss >= self.max_daily_loss_percent:
                return False, f"日亏损限制: {daily_loss:.2f}%"
        if self._current_drawdown >= self.max_drawdown_percent:
            return False, f"最大回撤: {self._current_drawdown:.2f}%"
            
        # 2. ⚡ 集群并发防线：如果准备开多仓，检查是否超过“最大同时持仓数”
        if side.upper() == "BUY":
            active_symbols = await position_manager.get_all_active_positions()
            # 如果该品种当前没有持仓，且总持仓数已满，则拦截
            if symbol not in active_symbols and len(active_symbols) >= self.max_active_trades:
                logger.warning(f"🛡️ [风控拦截] 拒绝买入 {symbol}，当前持仓品种已达上限 ({self.max_active_trades} 个)")
                return False, f"并发持仓数限制: {self.max_active_trades}"
                
        return True, "OK"
    
    def update_balance(self, current_balance: float) -> None:
        if current_balance > self._peak_balance:
            self._peak_balance = current_balance
        if self._peak_balance > 0:
            self._current_drawdown = (self._peak_balance - current_balance) / self._peak_balance * 100
    
    def get_risk_status(self) -> RiskStatus:
        start_balance = self._daily_start_balance
        if isinstance(start_balance, dict):
            start_balance = float(start_balance.get('total', {}).get('USDT', 0.0))
        else:
            start_balance = float(start_balance)
            
        pnl = float(self._daily_pnl) if isinstance(self._daily_pnl, (int, float)) else 0.0
        daily_loss = (abs(pnl) / start_balance * 100) if start_balance > 0 else 0.0
        
        risk_level = "low"
        can_trade = True
        if daily_loss >= self.max_daily_loss_percent * 0.8 or self._current_drawdown >= self.max_drawdown_percent * 0.8:
            risk_level = "high"
            can_trade = False
            
        return RiskStatus(
            daily_pnl=self._daily_pnl, 
            daily_loss_percent=daily_loss,
            current_drawdown=self._current_drawdown, 
            risk_level=risk_level, 
            can_trade=can_trade
        )

# 实例化全局单例
position_manager = PositionManager()
risk_manager = RiskManager()