#!/usr/bin/env python3
"""
币安自动交易系统 v3.0
主程序入口
"""
import asyncio
import sys
from typing import Optional

from core.config import config
from core.logger import logger
from core.database import db
from core.events import event_bus, EventType, Event

from data.sources import crypto_data_source
from data.processors import indicators
from data.storage import KlineStorage

from strategies import strategy_manager, ConvergenceBreakoutStrategy
from risk import position_manager, risk_manager
from execution import order_executor


class TradingEngine:
    """交易引擎"""
    
    def __init__(self):
        self._running = False
        self._tasks = []
        self._kline_storage: Optional[KlineStorage] = None
        self._last_kline_time: Optional[str] = None
    
    async def start(self) -> None:
        """启动交易引擎"""
        logger.info("=" * 60)
        logger.info("币安自动交易系统 v3.0 启动")
        logger.info(f"环境: {config.environment.value}")
        logger.info("=" * 60)
        
        self._running = True
        
        try:
            # 1. 连接数据库
            await db.connect()
            
            # 2. 连接交易所
            await crypto_data_source.connect()
            
            # 3. 初始化风险管理
            balance = await crypto_data_source.get_balance()
            await risk_manager.initialize(balance)
            await position_manager.update_balance(balance, balance)
            
            # 4. 初始化K线存储
            self._kline_storage = KlineStorage(
                symbol=config.trading.symbol,
                interval=config.trading.kline_interval
            )
            await self._kline_storage.initialize()
            
            # 5. 注册策略
            strategy_manager.register_strategy(ConvergenceBreakoutStrategy)
            strategy_manager.enable_strategy('convergence_breakout')
            
            # 6. 获取初始K线数据
            await self._fetch_initial_klines()
            
            # 7. 启动后台任务
            self._start_background_tasks()
            
            # 发布启动事件
            event_bus.publish(Event(
                event_type=EventType.SYSTEM_START,
                data={'balance': balance}
            ))
            
            logger.info("交易引擎启动完成")
            
        except Exception as e:
            logger.error(f"交易引擎启动失败: {e}")
            raise
    
    async def stop(self) -> None:
        """停止交易引擎"""
        logger.info("正在停止交易引擎...")
        
        self._running = False
        event_bus.stop()
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
        
        # 断开连接
        await crypto_data_source.disconnect()
        await db.close()
        
        logger.info("交易引擎已停止")
    
    async def _fetch_initial_klines(self) -> None:
        """获取初始K线数据"""
        klines = await crypto_data_source.get_klines(
            symbol=config.trading.symbol,
            interval=config.trading.kline_interval,
            limit=500
        )
        
        if klines:
            await self._kline_storage.add_klines(klines)
            logger.info(f"获取 {len(klines)} 根K线")
    
    def _start_background_tasks(self) -> None:
        """启动后台任务"""
        self._tasks = [
            asyncio.create_task(self._kline_polling_task()),
            asyncio.create_task(self._status_report_task()),
            asyncio.create_task(event_bus.start()),
        ]
    
    async def _kline_polling_task(self) -> None:
        """K线轮询任务"""
        await asyncio.sleep(5)
        
        while self._running:
            try:
                await asyncio.sleep(60)
                
                klines = await crypto_data_source.get_klines(
                    symbol=config.trading.symbol,
                    interval=config.trading.kline_interval,
                    limit=2
                )
                
                if not klines:
                    continue
                
                latest = klines[-1]
                kline_time = latest.open_time.isoformat()
                
                if self._last_kline_time != kline_time:
                    self._last_kline_time = kline_time
                    await self._kline_storage.add_klines([latest])
                    logger.info(f"K线更新: {kline_time}, 收盘价: {latest.close}")
                    await self._process_kline(latest)
            
            except Exception as e:
                logger.error(f"K线轮询错误: {e}")
                await asyncio.sleep(10)
    
    async def _process_kline(self, kline) -> None:
        """处理K线"""
        try:
            df = self._kline_storage.get_dataframe(limit=200)
            if df.empty:
                return
            
            df = indicators.add_all_indicators(df)
            position = await position_manager.get_position()
            signals = await strategy_manager.generate_signals(df, position)
            
            for signal in signals:
                await order_executor.execute_signal(signal)
            
            await self._update_balance()
        
        except Exception as e:
            logger.error(f"K线处理错误: {e}")
    
    async def _update_balance(self) -> None:
        """更新余额"""
        try:
            account = await crypto_data_source.get_account_info()
            balance = float(account.get('totalWalletBalance', 0))
            available = float(account.get('availableBalance', 0))
            await position_manager.update_balance(balance, available)
            risk_manager.update_balance(balance)
        except Exception as e:
            logger.error(f"更新余额失败: {e}")
    
    async def _status_report_task(self) -> None:
        """状态报告任务"""
        await asyncio.sleep(60)
        
        while self._running:
            try:
                balance = position_manager.balance
                risk_status = risk_manager.get_risk_status()
                logger.info(f"账户余额: {balance:.2f} USDT")
                logger.info(f"风险等级: {risk_status.risk_level}")
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"状态报告错误: {e}")


async def main():
    """主函数"""
    engine = TradingEngine()
    
    try:
        await engine.start()
        while engine._running:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    
    except Exception as e:
        logger.error(f"系统错误: {e}")
    
    finally:
        await engine.stop()


if __name__ == "__main__":
    try:
        config.validate()
    except Exception as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
