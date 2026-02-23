import asyncio
import ccxt  # 👈 【核心修复】引入 ccxt 以便捕获细分异常
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
        logger.info(f"开始处理信号: {signal.signal_type.name} | 标的: {signal.symbol} | 触发价: {signal.price}")
        if signal.signal_type == SignalType.BUY:
            return await self._spot_buy(signal)
        elif signal.signal_type == SignalType.SELL:
            return await self._spot_sell(signal)
        return None
    
    async def _spot_buy(self, signal: Signal) -> Optional[Trade]:
        # 【关键修复】如果信号自带了买入数量(比如我们的强行测试)，就听信号的！否则才去问风控。
        if signal.quantity and signal.quantity > 0:
            quantity = signal.quantity
        else:
            quantity = position_manager.calculate_position_size(price=signal.price)
            
        logger.info(f"准备买入数量: {quantity}")
        
        can_trade, reason = await risk_manager.check_pre_trade(signal.symbol, 'BUY', quantity, signal.price)
        if not can_trade:
            logger.warning(f"买入被风控拦截: {reason}")
            return None
        
        order = await self._place_order(signal.symbol, 'BUY', quantity)
        
        if not order or order.status != OrderStatus.FILLED:
            logger.error(f"买入订单彻底失败! 状态: {order.status if order else 'None'}, 原因: {order.error_message if order else '未知'}")
            return None
        
        trade = Trade(symbol=signal.symbol, side='BUY', entry_price=order.avg_price,
                     quantity=order.filled_quantity, strategy=signal.strategy_name, status='OPEN')
        trade.id = await db.save_trade(trade)
        self._trade_logger.info(f"成功买入 | {signal.symbol} | {order.filled_quantity:.6f} @ {order.avg_price:.2f}")
        return trade
    
    async def _spot_sell(self, signal: Signal) -> Optional[Trade]:
        position = await position_manager.get_position(signal.symbol)
        if not position:
            logger.warning(f"无法卖出 {signal.symbol}: 当前没有该资产的持仓。")
            return None
            
        quantity = signal.quantity if signal.quantity > 0 else position.get('quantity', 0)
        logger.info(f"准备卖出 {signal.symbol}, 数量: {quantity}")
        
        if quantity <= 0: return None
        
        order = await self._place_order(signal.symbol, 'SELL', quantity)
        if not order or order.status != OrderStatus.FILLED:
            logger.error(f"卖出订单彻底失败! 状态: {order.status if order else 'None'}, 原因: {order.error_message if order else '未知'}")
            return None
        
        open_trades = await db.get_open_trades(signal.symbol)
        pnl = 0
        entry_price = 0.0  # 默认值
        
        if open_trades:
            t = open_trades[0]
            entry_price = t['entry_price'] # 提取买入时的价格
            pnl = (order.avg_price - entry_price) * min(quantity, t['quantity'])
            await db.update_trade(t['id'], exit_price=order.avg_price, exit_time=datetime.now(), pnl=pnl, status='CLOSED')
        
        self._trade_logger.info(f"成功卖出 | {signal.symbol} | 盈亏: {pnl:.2f}")
        
        # 【关键修复】补齐 Trade 账本要求的必填项 entry_price 和 quantity
        return Trade(
            symbol=signal.symbol, 
            side='SELL', 
            entry_price=entry_price,  # 补上！
            quantity=quantity,        # 补上！
            exit_price=order.avg_price, 
            pnl=pnl, 
            status='CLOSED'
        )
    
    async def _place_order(self, symbol: str, side: str, quantity: float) -> Optional[Order]:
        logger.info(f"向交易所发送 API 请求 -> 标的: {symbol}, 方向: {side}, 数量: {quantity}")
        order = Order(symbol=symbol, side=side, quantity=quantity)
        
        for attempt in range(self._max_retries):
            try:
                result = await crypto_data_source._exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side.lower(),
                    amount=quantity
                )
                order.order_id = str(result.get('id'))
                order.status = OrderStatus.FILLED
                order.filled_quantity = float(result.get('filled', quantity))
                order.avg_price = float(result.get('average', 0))
                logger.info(f"API 下单成功! OrderID: {order.order_id}")
                return order
                
            # 👇【核心修复：智能熔断】区分网络错误和业务错误
            except ccxt.NetworkError as e:
                logger.warning(f"网络异常，准备重试 (尝试 {attempt + 1}/{self._max_retries}): {e}")
                order.error_message = str(e)
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
            except ccxt.ExchangeError as e:
                logger.error(f"交易所拒绝请求，停止重试: {e}")
                order.error_message = str(e)
                break  # 业务报错直接熔断，不再重试！
            except Exception as e:
                logger.error(f"发生未知严重错误: {e}")
                order.error_message = str(e)
                break
                    
        order.status = OrderStatus.FAILED
        return order

order_executor = OrderExecutor()