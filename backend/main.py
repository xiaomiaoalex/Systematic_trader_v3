#!/usr/bin/env python3
"""
币安自动交易系统 v3.0 - 多品种并发版
实现多品种独立轮询、数据隔离与并发执行逻辑
"""
import asyncio
import sys
import random
from typing import Optional, Dict
from datetime import datetime 
import pandas as pd

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
    """多品种并行交易引擎"""
    
    def __init__(self):
        self._running = False
        # 👇 核心重构 1：为每个品种分配独立的存储空间和时间游标
        self._storages: Dict[str, KlineStorage] = {}
        self._last_kline_times: Dict[str, str] = {}

    async def start(self) -> None:
        """初始化全局依赖"""
        logger.info("=" * 60)
        logger.info("币安自动交易系统 v3.0 [多品种并行版] 启动")
        logger.info(f"环境: {config.environment.value}")
        logger.info(f"监控目标: {', '.join(config.trading.symbols)}")
        logger.info("=" * 60)
        
        self._running = True
        
        try:
            # 1. 连接基础组件
            await db.connect()
            await crypto_data_source.connect()
            
            # 2. 初始化风险管理 (提取 USDT 余额)
            raw_balance = await crypto_data_source.get_account_info()
            total_usdt, free_usdt = self._extract_usdt_balance(raw_balance)
            
            await risk_manager.initialize(total_usdt)
            await position_manager.update_balance(total_usdt, free_usdt)
            
            # 👇 核心重构 2：循环初始化每个品种的存储与历史数据
            for symbol in config.trading.symbols:
                self._storages[symbol] = KlineStorage(
                    symbol=symbol,
                    interval=config.trading.kline_interval
                )
                await self._storages[symbol].initialize()
                # 获取初始 K 线时稍微错峰，防止触发布雷单限制
                await self._fetch_initial_klines(symbol)
                await asyncio.sleep(0.5) 
                
            # 3. 注册策略
            strategy_manager.register_strategy(ConvergenceBreakoutStrategy)
            strategy_manager.enable_strategy('convergence_breakout')
            
            # 4. 发布启动事件
            event_bus.publish(Event(
                event_type=EventType.SYSTEM_START,
                data={'balance': total_usdt, 'symbols': config.trading.symbols}
            ))
            
            logger.info(f"交易引擎初始化完成，已建立 {len(config.trading.symbols)} 个独立监控通道...")
            
        except Exception as e:
            logger.exception("[致命错误] 引擎启动失败，堆栈追踪如下：")
            raise

    def _extract_usdt_balance(self, account_info) -> tuple[float, float]:
        """安全提取 USDT 余额的辅助方法"""
        total = 0.0
        free = 0.0
        if isinstance(account_info, dict):
            total = float(account_info.get('total', {}).get('USDT', 0.0))
            free = float(account_info.get('free', {}).get('USDT', 0.0))
            if total == 0.0 and 'info' in account_info:
                total = float(account_info['info'].get('totalWalletBalance', 0.0))
                free = float(account_info['info'].get('availableBalance', 0.0))
        else:
            total = float(account_info) if account_info else 0.0
            free = total
        return total, free

    async def run_forever(self) -> None:
        """使用 TaskGroup 统一管理多品种并发任务"""
        try:
            async with asyncio.TaskGroup() as tg:
                # 👇 核心重构 3：为每一个交易对创建一个独立运行的轮询协程
                for index, symbol in enumerate(config.trading.symbols):
                    tg.create_task(self._kline_polling_task(symbol, index))
                
                # 启动全局监控与心跳任务
                tg.create_task(self._status_report_task())
                tg.create_task(event_bus.start())
                tg.create_task(self._heartbeat_task())
                
                logger.info("所有并行监控任务已在 TaskGroup 中启动 🚀")
        except ExceptionGroup as eg:
            logger.error(f"任务组异常终止，内部错误包含: {eg.exceptions}")
            raise

    async def stop(self) -> None:
        """停止交易引擎"""
        logger.info("正在停止多品种交易引擎...")
        self._running = False
        event_bus.stop()
        if crypto_data_source.is_connected:
            await crypto_data_source.disconnect()
        await db.close()
        logger.info("交易引擎已安全停止")

    async def _fetch_initial_klines(self, symbol: str) -> None:
        """获取单个品种的初始K线数据"""
        klines = await crypto_data_source.get_klines(
            symbol=symbol,
            interval=config.trading.kline_interval,
            limit=500
        )
        if klines is not None and not klines.empty:
            await self._storages[symbol].add_klines(klines)
            logger.info(f"[{symbol}] 成功加载 {len(klines)} 根历史 K 线")

    async def _kline_polling_task(self, symbol: str, index: int) -> None:
        """单个品种的 K 线并发轮询任务"""
        await asyncio.sleep(2)
        
        while self._running:
            try:
                # 精准时钟对齐逻辑
                now = datetime.now()
                sleep_seconds = 60 - now.second - now.microsecond / 1_000_000
                
                # 👇 API 防御：错峰请求。每个品种在前一个的基础上晚 0.2 秒去拉取
                jitter = 1.5 + (index * 0.2)
                await asyncio.sleep(sleep_seconds + jitter)
                
                klines = await crypto_data_source.get_klines(
                    symbol=symbol,
                    interval=config.trading.kline_interval,
                    limit=2
                )
                
                if klines is None or klines.empty:
                    continue
                
                latest = klines.iloc[-1]
                kline_time = pd.to_datetime(latest['open_time'], unit='ms').isoformat()
                
                # 读取该品种专属的上次更新时间
                last_time = self._last_kline_times.get(symbol)
                
                if last_time != kline_time:
                    self._last_kline_times[symbol] = kline_time
                    await self._storages[symbol].add_klines(klines.tail(1))
                    logger.info(f"📊 K线更新 [{symbol}]: {kline_time}, 收盘价: {latest.close}")
                    
                    # 触发该品种的处理逻辑
                    await self._process_kline(symbol, latest)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"💥 [{symbol}] 轮询报错: {e}")
                await asyncio.sleep(10)

    async def _process_kline(self, symbol: str, kline) -> None:
        """处理特定品种的 K 线并生成信号"""
        try:
            df = self._storages[symbol].get_dataframe(limit=200)
            if df.empty:
                return
            
            # 异步计算指标
            df = await asyncio.to_thread(indicators.add_all_indicators, df)
            
            # 仅获取当前处理品种的持仓状态
            position = await position_manager.get_position(symbol)
            signals = await strategy_manager.generate_signals(df, position)
            
            for signal in signals:
                # 👇 信号强转机制：防止策略文件里写死了 config.trading.symbol
                signal.symbol = symbol 
                await order_executor.execute_signal(signal)
            
            # 每次处理完可能下单后，更新一次全局余额
            if signals:
                await self._update_balance()
                
        except Exception as e:
            logger.error(f"[{symbol}] K线处理错误: {e}")

    async def _update_balance(self) -> None:
        """更新全局余额"""
        try:
            account = await crypto_data_source.get_account_info()
            total_balance, free_balance = self._extract_usdt_balance(account)
            await position_manager.update_balance(total_balance, free_balance)
            risk_manager.update_balance(total_balance)
        except Exception as e:
            logger.error(f"更新余额异常: {e}")

    async def _status_report_task(self) -> None:
        """状态报告任务：定时打印资产与所有品种持仓"""
        await asyncio.sleep(10)
        
        while self._running:
            try:
                balance = position_manager.balance
                usdt_balance = float(balance.get('total', {}).get('USDT', 0.0)) if isinstance(balance, dict) else float(balance)
                risk_status = risk_manager.get_risk_status()
                
                # 遍历组装多持仓日志
                active_positions = []
                for symbol in config.trading.symbols:
                    pos = await position_manager.get_position(symbol)
                    pos_qty = float(pos.get('quantity', 0.0)) if pos else 0.0
                    if pos_qty > 0:
                        active_positions.append(f"{symbol}:{pos_qty:.5f}")
                
                pos_str = f" | 📦 持仓: {', '.join(active_positions)}" if active_positions else " | ⚪ 当前空仓"
                log_msg = f"💰 余额: {usdt_balance:.2f} USDT{pos_str} | 🛡️ 风险: {risk_status.risk_level}"
                logger.info(log_msg)
                
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"状态报告异常: {e}")
                await asyncio.sleep(10)

    async def _heartbeat_task(self):
        """心跳任务"""
        while True:
            logger.info("💓 引擎心跳：滴答... (多品种雷达扫描中)")
            await asyncio.sleep(3600)

async def main():
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
        pass