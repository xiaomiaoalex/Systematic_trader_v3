"""
API服务器 - 动态任务调度版
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Dict, Optional

from core.config import config
from core.logger import logger
from core.database import db
from core.events import event_bus, EventType, Event
from data.sources import crypto_data_source
from strategies import strategy_manager, ConvergenceBreakoutStrategy
from risk import risk_manager, position_manager
from backtest import backtest_engine

def create_app() -> FastAPI:
    """创建FastAPI应用"""
    
    app = FastAPI(
        title="Trading System API",
        version="3.0.0",
        docs_url="/docs",
        openapi_url="/openapi.json"
    )
    
    # CORS 跨域配置：确保前端 8000/3000 端口可以访问后端 8080
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ================= 系统状态 =================
    @app.get("/api/status")
    async def get_status():
        return {"running": crypto_data_source.is_connected, "version": "3.0.0"}
    
    # ================= 交易对管理 (热插拔) =================
    @app.get("/api/symbols")
    async def get_symbols():
        """获取当前正在监控的品种列表"""
        return {"symbols": config.trading.symbols}

    @app.post("/api/symbols/{symbol}")
    async def add_symbol(symbol: str):
        """挂载新交易对"""
        symbol = symbol.upper()
        if symbol in config.trading.symbols:
            raise HTTPException(400, "该品种已经在监控列表中")
        
        # 通过事件总线发布添加指令
        event_bus.publish(Event(event_type=EventType.ADD_SYMBOL, data={'symbol': symbol}))
        return {"success": True, "message": f"已触发挂载 {symbol} 的指令"}

    @app.delete("/api/symbols/{symbol}")
    async def remove_symbol(symbol: str):
        """卸载交易对"""
        symbol = symbol.upper()
        if symbol not in config.trading.symbols:
            raise HTTPException(400, "该品种不在监控列表中")
            
        # 通过事件总线发布移除指令
        event_bus.publish(Event(event_type=EventType.REMOVE_SYMBOL, data={'symbol': symbol}))
        return {"success": True, "message": f"已触发卸载 {symbol} 的指令"}
    
    # ================= 账户与余额 =================
    @app.get("/api/account")
    async def get_account():
        try:
            return await crypto_data_source.get_account_info()
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            raise HTTPException(500, str(e))

    @app.get("/api/account/balance")
    async def get_account_balance():
        """新增：专门用于获取余额的接口，对应前端 API.getBalance()"""
        try:
            # 直接返回底层账户信息，前端 app.js 已适配解析逻辑
            return await crypto_data_source.get_account_info()
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/positions")
    async def get_positions():
        """获取真实持仓数据"""
        try:
            # 核心修复：直接从数据库查询处于 'OPEN' 状态的持仓记录
            return await db.get_open_trades()
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            raise HTTPException(500, str(e))
    
    @app.get("/api/trades")
    async def get_trades(limit: int = 50):
        try:
            return await db.get_recent_trades(limit)
        except Exception as e:
            logger.error(f"获取成交历史失败: {e}")
            raise HTTPException(500, str(e))
    
    # ================= 策略管理 =================
    @app.get("/api/strategies")
    async def get_strategies():
        strategies = []
        for name, s in strategy_manager._strategies.items():
            stats = s.get_stats()
            strategies.append({
                'name': name, 
                'version': s.VERSION, 
                'description': s.DESCRIPTION,
                'enabled': s.is_enabled, 
                'params': s.params,
                'signalCount': stats['signal_count'], 
                'winRate': stats['win_rate']
            })
        return strategies
    
    @app.post("/api/strategies/{name}/enable")
    async def enable_strategy(name: str):
        return {"success": strategy_manager.enable_strategy(name)}
    
    @app.post("/api/strategies/{name}/disable")
    async def disable_strategy(name: str):
        return {"success": strategy_manager.disable_strategy(name)}
    
    @app.put("/api/strategies/{name}/params")
    async def update_strategy_params(name: str, params: dict):
        """更新策略运行参数"""
        strategy = strategy_manager.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"找不到策略: {name}")
        
        try:
            strategy.update_params(params)
            logger.info(f"⚙️ 策略 [{name}] 参数已动态更新: {params}")
            return {
                "success": True, 
                "message": f"策略 {name} 参数更新成功",
                "new_params": strategy.params
            }
        except Exception as e:
            logger.error(f"更新策略参数失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ================= 回测系统 =================
    @app.post("/api/backtest/run")
    async def run_backtest(request: dict):
        try:
            import pandas as pd
            import math
            import datetime # 👈 新增 datetime 模块
            
            symbol = request.get('symbol', 'BTCUSDT').replace('/', '')
            interval = request.get('interval', '1h')
            
            # 👇 核心升级：读取前后端约定的时间参数
            start_time_str = request.get('startTime')
            end_time_str = request.get('endTime')
            
            if start_time_str and end_time_str:
                # 将 "2023-01-01" 转换为毫秒时间戳
                start_ts = int(datetime.datetime.strptime(start_time_str, '%Y-%m-%d').timestamp() * 1000)
                # 结束时间默认包含当天的 23:59:59
                end_ts = int((datetime.datetime.strptime(end_time_str, '%Y-%m-%d') + datetime.timedelta(days=1)).timestamp() * 1000) - 1
                
                # 调用全新的分页引擎
                df = await crypto_data_source.get_historical_klines(symbol, interval, start_ts, end_ts)
            else:
                # 兼容旧版本，没传时间就拉取最近 500 根
                df = await crypto_data_source.get_klines(symbol, interval, 500)
            
            if df is None or df.empty:
                raise HTTPException(400, "无法获取该时间段的 K 线数据，可能是超出了交易所历史范围")
            
            # ... 下面的策略准备和数据净化代码保持完全不变 ...
            strategy_name = request.get('strategy', 'convergence_breakout')
            strategy = strategy_manager.get_strategy(strategy_name)
            
            if not strategy:
                from strategies.convergence_breakout import ConvergenceBreakoutStrategy
                strategy = ConvergenceBreakoutStrategy()
            
            result = await backtest_engine.run(strategy, df)
            
            def clean_float(val):
                if pd.isna(val) or math.isnan(val): return 0.0
                if math.isinf(val): return 999.99 if val > 0 else 0.0 
                return val
            
            return {
                'totalReturn': clean_float(result.total_return),
                'annualReturn': clean_float(result.annual_return),
                'maxDrawdown': clean_float(result.max_drawdown),
                'sharpeRatio': clean_float(result.sharpe_ratio),
                'winRate': clean_float(result.win_rate),
                'profitFactor': clean_float(result.profit_factor),
                'totalTrades': result.total_trades,
                'trades': result.trades[:100]
            }
        except Exception as e:
            logger.error(f"回测运行失败: {e}")
            raise HTTPException(500, str(e))
    
    # ================= 风险管理 =================
    @app.get("/api/risk/status")
    async def get_risk_status():
        status = risk_manager.get_risk_status()
        return {
            'dailyPnl': status.daily_pnl, 
            'dailyLossPercent': status.daily_loss_percent,
            'currentDrawdown': status.current_drawdown, 
            'riskLevel': status.risk_level
        }
    
    # ================= K线数据 =================
    @app.get("/api/klines")
    async def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 500):
        try:
            klines = await crypto_data_source.get_klines(symbol, interval, limit)
            return [k.to_dict() for k in klines]
        except Exception as e:
            logger.error(f"获取K线失败: {e}")
            raise HTTPException(500, str(e))
    
    # 静态文件挂载
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")
    
    return app