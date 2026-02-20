import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
from core.logger import logger, get_trade_logger
from core.database import db, Trade
from strategies.base import Signal, SignalType
from data.sources import crypto_data_source
from risk import position_manager, risk_manager

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    FAILED = "FAILED"

@dataclass
class Order:
    order_id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    error_message: str = ""

class OrderExecutor:
    def __init__(self, max_retries: int = 3):
        self._trade_logger = get_trade_logger()
        self._max_retries = max_retries
    
    async def execute_signal(self, signal: Signal) -> Optional[Trade]:
        logger.info(f"执行信号: {signal.signal_type.name}")
        if signal.signal_type == SignalType.BUY:
            return await self._spot_buy(signal)
        elif signal.signal_type == SignalType.SELL:
            return await self._spot_sell(signal)
        return None
    
    async def _spot_buy(self, signal: Signal) -> Optional[Trade]:
        quantity = position_manager.calculate_position_size(price=signal.price)
        can_trade, reason = await risk_manager.check_pre_trade(signal.symbol, 'BUY', quantity, signal.price)
        if not can_trade:
            logger.warning(f"买入被拒绝: {reason}")
            return None
        
        order = await self._place_order(signal.symbol, 'BUY', quantity)
        if not order or order.status != OrderStatus.FILLED:
            return None
        
        trade = Trade(symbol=signal.symbol, side='BUY', entry_price=order.avg_price,
                     quantity=order.filled_quantity, strategy=signal.strategy_name, status='OPEN')
        trade.id = await db.save_trade(trade)
        self._trade_logger.info(f"买入 | {signal.symbol} | {order.filled_quantity:.6f} @ {order.avg_price:.2f}")
        return trade
    
    async def _spot_sell(self, signal: Signal) -> Optional[Trade]:
        position = await position_manager.get_position(signal.symbol)
        if not position: return None
        quantity = signal.quantity if signal.quantity > 0 else position.get('quantity', 0)
        if quantity <= 0: return None
        
        order = await self._place_order(signal.symbol, 'SELL', quantity)
        if not order or order.status != OrderStatus.FILLED: return None
        
        open_trades = await db.get_open_trades(signal.symbol)
        pnl = 0
        if open_trades:
            t = open_trades[0]
            pnl = (order.avg_price - t['entry_price']) * min(quantity, t['quantity'])
            await db.update_trade(t['id'], exit_price=order.avg_price, exit_time=datetime.now(), pnl=pnl, status='CLOSED')
        
        self._trade_logger.info(f"卖出 | {signal.symbol} | 盈亏: {pnl:.2f}")
        return Trade(symbol=signal.symbol, side='SELL', exit_price=order.avg_price, pnl=pnl, status='CLOSED')
    
    async def _place_order(self, symbol: str, side: str, quantity: float) -> Optional[Order]:
        order = Order(symbol=symbol, side=side, quantity=quantity)
        for attempt in range(self._max_retries):
            try:
                result = await crypto_data_source.place_order(symbol, side, 'MARKET', quantity)
                order.order_id = str(result.get('orderId'))
                order.status = OrderStatus.FILLED
                order.filled_quantity = float(result.get('filled', quantity))
                order.avg_price = float(result.get('average', 0))
                return order
            except Exception as e:
                order.error_message = str(e)
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        order.status = OrderStatus.FAILED
        return order

order_executor = OrderExecutor()
