"""
API服务器
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
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    @app.get("/api/status")
    async def get_status():
        return {"running": crypto_data_source.is_connected, "version": "3.0.0"}
    
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
        
        # 通过总线发布指令，完美避开循环依赖
        event_bus.publish(Event(event_type=EventType.ADD_SYMBOL, data={'symbol': symbol}))
        return {"success": True, "message": f"已触发挂载 {symbol} 的指令"}

    @app.delete("/api/symbols/{symbol}")
    async def remove_symbol(symbol: str):
        """卸载交易对"""
        symbol = symbol.upper()
        if symbol not in config.trading.symbols:
            raise HTTPException(400, "该品种不在监控列表中")
            
        event_bus.publish(Event(event_type=EventType.REMOVE_SYMBOL, data={'symbol': symbol}))
        return {"success": True, "message": f"已触发卸载 {symbol} 的指令"}
    
    @app.get("/api/account")
    async def get_account():
        try:
            return await crypto_data_source.get_account_info()
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @app.get("/api/positions")
    async def get_positions():
        try:
            return await crypto_data_source.get_positions()
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @app.get("/api/trades")
    async def get_trades(limit: int = 50):
        try:
            return await db.get_recent_trades(limit)
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @app.get("/api/strategies")
    async def get_strategies():
        strategies = []
        for name, s in strategy_manager._strategies.items():
            stats = s.get_stats()
            strategies.append({
                'name': name, 'version': s.VERSION, 'description': s.DESCRIPTION,
                'enabled': s.is_enabled, 'params': s.params,
                'signalCount': stats['signal_count'], 'winRate': stats['win_rate']
            })
        return strategies
    
    @app.post("/api/strategies/{name}/enable")
    async def enable_strategy(name: str):
        return {"success": strategy_manager.enable_strategy(name)}
    
    @app.post("/api/strategies/{name}/disable")
    async def disable_strategy(name: str):
        return {"success": strategy_manager.disable_strategy(name)}
    
    # 👇 ================= 新增：动态修改策略参数 API ================= 👇
    @app.put("/api/strategies/{name}/params")
    async def update_strategy_params(name: str, params: dict):
        strategy = strategy_manager.get_strategy(name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"找不到策略: {name}")
        
        try:
            # 调用 base.py 中已有的 update_params 方法
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
    # 👆 ============================================================= 👆

    @app.post("/api/backtest/run")
    async def run_backtest(request: dict):
        try:
            import pandas as pd
            klines = await crypto_data_source.get_klines(
                request.get('symbol', 'BTCUSDT'),
                request.get('interval', '1h'), 500
            )
            if not klines:
                raise HTTPException(400, "No data")
            
            data = [{'open_time': k.open_time, 'open': k.open, 'high': k.high,
                    'low': k.low, 'close': k.close, 'volume': k.volume} for k in klines]
            df = pd.DataFrame(data)
            df.set_index('open_time', inplace=True)
            
            strategy = strategy_manager.get_strategy(request.get('strategy', 'convergence_breakout'))
            if not strategy:
                strategy = ConvergenceBreakoutStrategy()
            
            result = await backtest_engine.run(strategy, df)
            
            return {
                'totalReturn': result.total_return, 'annualReturn': result.annual_return,
                'maxDrawdown': result.max_drawdown, 'sharpeRatio': result.sharpe_ratio,
                'winRate': result.win_rate, 'profitFactor': result.profit_factor,
                'totalTrades': result.total_trades, 'trades': result.trades[:100]
            }
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @app.get("/api/risk/status")
    async def get_risk_status():
        status = risk_manager.get_risk_status()
        return {
            'dailyPnl': status.daily_pnl, 'dailyLossPercent': status.daily_loss_percent,
            'currentDrawdown': status.current_drawdown, 'riskLevel': status.risk_level
        }
    
    @app.get("/api/klines")
    async def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 500):
        try:
            klines = await crypto_data_source.get_klines(symbol, interval, limit)
            return [k.to_dict() for k in klines]
        except Exception as e:
            raise HTTPException(500, str(e))
    
    # 静态文件
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")
    
    return app


def run_server():
    """运行服务器"""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=config.api.host, port=config.api.port)
