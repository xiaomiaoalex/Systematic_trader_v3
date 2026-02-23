#!/usr/bin/env python3
"""
币安自动交易系统 v3.0 - 动态任务调度版 (热插拔)
实现运行时无缝增删交易对、自动同步配置文件与 API 内嵌同源
"""
import asyncio
import sys
import uvicorn
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
from api.server import create_app

class TradingEngine:
    """支持热插拔的超级交易引擎"""
    
    def __init__(self):
        self._running = False
        self._storages: Dict[str, KlineStorage] = {}
        self._last_kline_times: Dict[str, str] = {}
        # 👇 动态任务池：专门用于管理可以随时启停的子任务
        self._active_tasks: Dict[str, asyncio.Task] = {} 
        self._tg: Optional[asyncio.TaskGroup] = None

    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("币安自动交易系统 v3.0 [动态热插拔版] 启动")
        logger.info(f"环境: {config.environment.value}")
        logger.info("=" * 60)
        
        self._running = True
        
        # 🔌 订阅总线上的热插拔指令
        event_bus.subscribe(EventType.ADD_SYMBOL, self._handle_add_symbol)
        event_bus.subscribe(EventType.REMOVE_SYMBOL, self._handle_remove_symbol)
        
        try:
            await db.connect()
            await crypto_data_source.connect()
            
            raw_balance = await crypto_data_source.get_account_info()
            total_usdt, free_usdt = self._extract_usdt_balance(raw_balance)
            
            await risk_manager.initialize(total_usdt)
            await position_manager.update_balance(total_usdt, free_usdt)
            
            # 初始化开局名单
            for symbol in config.trading.symbols:
                await self._init_symbol_storage(symbol)
                await asyncio.sleep(0.5) 
                
            strategy_manager.register_strategy(ConvergenceBreakoutStrategy)
            strategy_manager.enable_strategy('convergence_breakout')
            
            event_bus.publish(Event(
                event_type=EventType.SYSTEM_START,
                data={'balance': total_usdt, 'symbols': config.trading.symbols}
            ))
            
        except Exception as e:
            logger.exception("[致命错误] 引擎启动失败：")
            raise

    async def _init_symbol_storage(self, symbol: str) -> None:
        """封装存储初始化，方便热插拔复用"""
        if symbol not in self._storages:
            self._storages[symbol] = KlineStorage(symbol, interval=config.trading.kline_interval)
            await self._storages[symbol].initialize()
            await self._fetch_initial_klines(symbol)

    # ================= 热插拔核心逻辑 =================
    async def _handle_add_symbol(self, event: Event) -> None:
        symbol = event.data.get('symbol')
        if not symbol or symbol in self._active_tasks:
            return

        logger.info(f"🚀 [动态调度] 收到指令，正在为您分配 {symbol} 的独立计算资源...")

        # 1. 内存与磁盘持久化同步
        if symbol not in config.trading.symbols:
            config.trading.symbols.append(symbol)
            self._update_env_file("SYMBOLS", ",".join(config.trading.symbols))

        # 2. 拉取历史弹药
        await self._init_symbol_storage(symbol)

        # 3. 动态将新协程注入正在运行的 TaskGroup 中！
        if self._tg:
            task = self._tg.create_task(self._kline_polling_task(symbol, len(self._active_tasks)))
            self._active_tasks[symbol] = task

        logger.info(f"✅ [动态调度] {symbol} 挂载成功，已无缝接入雷达扫描网！")

    async def _handle_remove_symbol(self, event: Event) -> None:
        symbol = event.data.get('symbol')
        if not symbol or symbol not in self._active_tasks:
            return

        logger.info(f"🪓 [动态调度] 正在强制阻断并卸载 {symbol} 的监控流...")

        # 1. 精准狙杀后台协程
        task = self._active_tasks.pop(symbol)
        task.cancel() 

        # 2. 清理内存名单与磁盘配置
        if symbol in config.trading.symbols:
            config.trading.symbols.remove(symbol)
            self._update_env_file("SYMBOLS", ",".join(config.trading.symbols))

        # 3. 释放数据库连接与内存 DataFrame
        if symbol in self._storages:
            del self._storages[symbol]

        logger.info(f"⛔ [动态调度] {symbol} 已彻底下线。")

    def _update_env_file(self, key: str, value: str) -> None:
        """黑客级持久化：直接修改底层 .env 文件"""
        try:
            env_file = config.project_root / "backend" / f".env.{config.environment.value}"
            if not env_file.exists():
                env_file = config.project_root / "backend" / ".env"
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                with open(env_file, 'w', encoding='utf-8') as f:
                    for line in lines:
                        if line.startswith(f"{key}="):
                            f.write(f"{key}={value}\n")
                        else:
                            f.write(line)
        except Exception as e:
            logger.error(f"持久化写入 .env 失败: {e}")
    # =================================================

    def _extract_usdt_balance(self, account_info) -> tuple[float, float]:
        total = free = 0.0
        if isinstance(account_info, dict):
            total = float(account_info.get('total', {}).get('USDT', 0.0))
            free = float(account_info.get('free', {}).get('USDT', 0.0))
            if total == 0.0 and 'info' in account_info:
                total = float(account_info['info'].get('totalWalletBalance', 0.0))
                free = float(account_info['info'].get('availableBalance', 0.0))
        else:
            total = free = float(account_info) if account_info else 0.0
        return total, free

    async def run_forever(self) -> None:
        """统一管理所有的后台生命周期"""
        try:
            async with asyncio.TaskGroup() as tg:
                self._tg = tg  # 👈 挂载引用，允许热插拔时动态借道

                # 1. 启动交易对监控大军
                for index, symbol in enumerate(config.trading.symbols):
                    task = tg.create_task(self._kline_polling_task(symbol, index))
                    self._active_tasks[symbol] = task
                
                # 2. 启动系统后勤
                tg.create_task(self._status_report_task())
                tg.create_task(event_bus.start())
                tg.create_task(self._heartbeat_task())
                
                # 3. 🌐 将 API 服务器内嵌入主循环！
                logger.info(f"🌐 正在内嵌启动 API 节点 (端口: {config.api.port})...")
                api_config = uvicorn.Config(create_app(), host=config.api.host, port=config.api.port, log_config=None)
                api_server = uvicorn.Server(api_config)
                tg.create_task(api_server.serve())

                logger.info("所有微服务 (引擎、雷达、API) 已融合入单核生命周期 🚀")
                
        except ExceptionGroup as eg:
            logger.error(f"任务组异常: {eg.exceptions}")
            raise

    async def stop(self) -> None:
        logger.info("正在停止多品种交易引擎...")
        self._running = False
        event_bus.stop()
        if crypto_data_source.is_connected:
            await crypto_data_source.disconnect()
        await db.close()
        logger.info("交易引擎已安全停止")

    async def _fetch_initial_klines(self, symbol: str) -> None:
        klines = await crypto_data_source.get_klines(
            symbol=symbol, interval=config.trading.kline_interval, limit=500
        )
        if klines is not None and not klines.empty:
            await self._storages[symbol].add_klines(klines)
            logger.info(f"[{symbol}] 成功加载 {len(klines)} 根历史弹药")

    async def _kline_polling_task(self, symbol: str, index: int) -> None:
        await asyncio.sleep(2)
        while self._running:
            try:
                now = datetime.now()
                sleep_seconds = 60 - now.second - now.microsecond / 1_000_000
                jitter = 1.5 + (index * 0.2)
                await asyncio.sleep(sleep_seconds + jitter)
                
                klines = await crypto_data_source.get_klines(
                    symbol=symbol, interval=config.trading.kline_interval, limit=2
                )
                if klines is None or klines.empty: continue
                
                latest = klines.iloc[-1]
                kline_time = pd.to_datetime(latest['open_time'], unit='ms').isoformat()
                
                if self._last_kline_times.get(symbol) != kline_time:
                    self._last_kline_times[symbol] = kline_time
                    await self._storages[symbol].add_klines(klines.tail(1))
                    logger.info(f"📊 K线更新 [{symbol}]: {kline_time}, 现价: {latest.close}")
                    await self._process_kline(symbol, latest)
            
            except asyncio.CancelledError:
                # 优雅响应 cancel 信号
                logger.info(f"🔌 协程 [{symbol}] 已安全中断。")
                break
            except Exception as e:
                logger.error(f"💥 [{symbol}] 轮询报错: {e}")
                await asyncio.sleep(10)

    async def _process_kline(self, symbol: str, kline) -> None:
        try:
            df = self._storages[symbol].get_dataframe(limit=200)
            if df.empty: return
            
            df = await asyncio.to_thread(indicators.add_all_indicators, df)
            position = await position_manager.get_position(symbol)
            signals = await strategy_manager.generate_signals(df, position)
            
            for signal in signals:
                signal.symbol = symbol 
                await order_executor.execute_signal(signal)
            
            if signals: await self._update_balance()
                
        except Exception as e:
            logger.error(f"[{symbol}] 策略计算错误: {e}")

    async def _update_balance(self) -> None:
        try:
            account = await crypto_data_source.get_account_info()
            total_balance, free_balance = self._extract_usdt_balance(account)
            await position_manager.update_balance(total_balance, free_balance)
            risk_manager.update_balance(total_balance)
        except Exception as e:
            logger.error(f"更新余额异常: {e}")

    async def _status_report_task(self) -> None:
        await asyncio.sleep(10)
        while self._running:
            try:
                balance = position_manager.balance
                usdt_balance = float(balance.get('total', {}).get('USDT', 0.0)) if isinstance(balance, dict) else float(balance)
                risk_status = risk_manager.get_risk_status()
                
                active_positions = []
                # 动态读取当前存活的任务池，确保与热插拔名单严格同步
                for symbol in list(self._active_tasks.keys()):
                    pos = await position_manager.get_position(symbol)
                    pos_qty = float(pos.get('quantity', 0.0)) if pos else 0.0
                    if pos_qty > 0:
                        active_positions.append(f"{symbol}:{pos_qty:.5f}")
                
                pos_str = f" | 📦: {', '.join(active_positions)}" if active_positions else " | ⚪"
                # 增加雷达数量显示
                radar_str = f" | 📡 监控 {len(self._active_tasks)} 个品种"
                
                logger.info(f"💰 余额: {usdt_balance:.2f} USDT{pos_str}{radar_str} | 🛡️ {risk_status.risk_level}")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"状态报告异常: {e}")
                await asyncio.sleep(10)

    async def _heartbeat_task(self):
        while True:
            logger.info("💓 引擎心跳：滴答...")
            await asyncio.sleep(3600)

async def main():
    engine = TradingEngine()
    try:
        await engine.start()
        await engine.run_forever()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    finally:
        await engine.stop()

if __name__ == "__main__":
    try:
        config.validate()
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass