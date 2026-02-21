import asyncio
from core.config import config
from data.sources import crypto_data_source
from execution.executor import order_executor
from core.database import db  # 引入数据库实例

# 根据你的 base.py 结构导入
from strategies.base import Signal, SignalType

async def main():
    print("=" * 60)
    print("🚀 [实盘链路穿透测试] 伪造信号发射程序启动")
    print(f"⚠️ 当前环境: {config.environment.value} (请确认是测试网！)")
    print("=" * 60)
    
    try:
        # 0. 【关键修复】给数据库通电！
        print("💾 正在连接本地数据库...")
        await db.connect()
        
        # 1. 建立与交易所的物理连接
        print("🔌 正在连接交易所...")
        await crypto_data_source.connect()
        
        # 2. 获取一下最新价格
        print(f"🔍 正在获取 {config.trading.symbol} 最新市价...")
        ticker = await crypto_data_source._exchange.fetch_ticker(config.trading.symbol)
        current_price = ticker['last']
        print(f"💰 最新市价: {current_price} USDT")
        
        # 3. 组装一颗“穿甲弹”
        fake_signal = Signal(
            strategy_name="test_fire_shooter",
            signal_type=SignalType.SELL,
            symbol=config.trading.symbol,
            price=current_price,
            quantity=0.005,  # 强制买入数量
            metadata={"reason": "穿透测试：无视策略，强制开火！"} 
        )
        
        # 4. 扣动扳机！把信号强行塞给订单执行器
        print(f"\n🎯 [开火指令] 正在向 order_executor 推送 BUY 信号...")
        await order_executor.execute_signal(fake_signal)
        print("\n✅ 指令已推送给执行器！请观察下方日志输出。")
        
    except Exception as e:
        print(f"\n❌ 发射过程发生致命错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 5. 打完收工，断开所有连接
        print("🛑 正在断开连接并清理战场...")
        if crypto_data_source.is_connected:
            await crypto_data_source.disconnect()
        await db.close() # 【关键修复】拔掉数据库电源

if __name__ == "__main__":
    asyncio.run(main())