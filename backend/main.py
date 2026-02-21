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
        self._kline_storage: Optional[KlineStorage] = None
        self._last_kline_time: Optional[str] = None
    
    async def start(self) -> None:
        """初始化并启动交易引擎的依赖"""
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
            
            # 👇 ====== 3. 初始化风险管理 (开局纯净版) ====== 👇
            raw_balance = await crypto_data_source.get_account_info()
            
            total_usdt = 0.0
            free_usdt = 0.0
            if isinstance(raw_balance, dict):
                total_usdt = float(raw_balance.get('total', {}).get('USDT', 0.0))
                free_usdt = float(raw_balance.get('free', {}).get('USDT', 0.0))
                if total_usdt == 0.0 and 'info' in raw_balance:
                    total_usdt = float(raw_balance['info'].get('totalWalletBalance', 0.0))
                    free_usdt = float(raw_balance['info'].get('availableBalance', 0.0))
            else:
                total_usdt = float(raw_balance) if raw_balance else 0.0
                free_usdt = total_usdt
                
            await risk_manager.initialize(total_usdt)
            await position_manager.update_balance(total_usdt, free_usdt)
            # 👆 ============================================== 👆
            
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
            
            # 发布启动事件
            event_bus.publish(Event(
                event_type=EventType.SYSTEM_START,
                data={'balance': total_usdt}
            ))
            
            logger.info("交易引擎初始化完成，准备启动后台任务...")
            
        except Exception as e:
            logger.exception("[致命错误] 引擎启动失败，堆栈追踪如下：")
            raise

    async def run_forever(self) -> None:
        """使用 TaskGroup 统一管理后台任务的生命周期"""
        try:
            async with asyncio.TaskGroup() as tg:
                # 将后台任务加入任务组
                tg.create_task(self._kline_polling_task())
                tg.create_task(self._status_report_task())
                tg.create_task(event_bus.start())
                tg.create_task(self._heartbeat_task())
                
                logger.info("所有后台任务已在 TaskGroup 中启动")
        except ExceptionGroup as eg:
            # 捕获任务组中的异常 (Python 3.11+)
            logger.error(f"任务组异常终止，内部错误包含: {eg.exceptions}")
            raise
    
    async def stop(self) -> None:
        """停止交易引擎"""
        logger.info("正在停止交易引擎...")
        
        self._running = False
        event_bus.stop()
        
        # 断开连接
        if crypto_data_source.is_connected:
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
        
        if klines is not None and not klines.empty:
            await self._kline_storage.add_klines(klines)
            logger.info(f"获取 {len(klines)} 根K线")
    
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
                
                if klines is None or klines.empty:
                    continue
                
                if klines is None or klines.empty:
                    logger.debug("行情平静，当前周期无新交易数据产生。")
                    continue  # 直接跳过，等下一个轮回
                
            # 使用 .iloc 按位置提取最后一行，完美解决 KeyError
                latest = klines.iloc[-1]
                # 👇 ====== 将毫秒数字转化为标准时间格式 ====== 👇
                import pandas as pd
                kline_time = pd.to_datetime(latest['open_time'], unit='ms').isoformat()
                # 👆 ========================================== 👆
                
                if self._last_kline_time != kline_time:
                    self._last_kline_time = kline_time
                    # 👇 ====== 直接切下最后一根 K 线作为 DataFrame 传入 ====== 👇
                    await self._kline_storage.add_klines(klines.tail(1))
                    logger.info(f"K线更新: {kline_time}, 收盘价: {latest.close}")
                    await self._process_kline(latest)
            
            except asyncio.CancelledError:
                # 任务组被取消时安全退出
                break
            except Exception as e:
                logger.exception("💥 抓到你了！K线轮询报错的完整堆栈如下：")
                # 遇到非致命错误时，稍作等待继续重试
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
        """更新余额 (双保险提纯版)"""
        try:
            account = await crypto_data_source.get_account_info()
            
            # 👇 ====== 极速海关：兼容标准 CCXT 格式与币安原生格式 ====== 👇
            total_balance = 0.0
            free_balance = 0.0
            
            if isinstance(account, dict):
                # 方案 A: 使用 CCXT 标准字典提取 USDT
                total_balance = float(account.get('total', {}).get('USDT', 0.0))
                free_balance = float(account.get('free', {}).get('USDT', 0.0))
                
                # 方案 B: 如果标准提取是 0，尝试去底层的 'info' 原始数据里捞 (针对合约账户)
                if total_balance == 0.0 and 'info' in account:
                    info_dict = account['info']
                    total_balance = float(info_dict.get('totalWalletBalance', total_balance))
                    free_balance = float(info_dict.get('availableBalance', free_balance))
            # 👆 ======================================================== 👆
            
            # 安全更新风控系统
            await position_manager.update_balance(total_balance, free_balance)
            risk_manager.update_balance(total_balance)
            
        except Exception as e:
            logger.exception("💥 更新余额发生异常，堆栈追踪：")
    
    async def _status_report_task(self) -> None:
        """状态报告任务"""
        await asyncio.sleep(60)
        
        while self._running:
            try:
                balance = position_manager.balance
                risk_status = risk_manager.get_risk_status()
                # 👇 ====== 优雅提取 USDT 余额 ====== 👇
                usdt_balance = float(balance.get('total', {}).get('USDT', 0.0)) if isinstance(balance, dict) else float(balance)
                logger.info(f"账户余额: {usdt_balance:.2f} USDT")
                logger.info(f"风险等级: {risk_status.risk_level}")
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("💥 状态报告错误堆栈：")

    async def _heartbeat_task(self):
        """专门用来证明系统还活着的‘心跳’任务"""
        while True:
            logger.info(" 引擎心跳：滴答... (系统正在后台安稳等待新行情)")
            await asyncio.sleep(3600)  # 每隔 10 秒钟跳一次，你可以改成 5 或 60

async def main():
    """主函数"""
    engine = TradingEngine()
    
    try:
        await engine.start()
        await engine.run_forever()
    
    except asyncio.CancelledError:
        logger.info("主程序任务被取消...")
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
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 防止退出时打印不必要的 Traceback
        pass