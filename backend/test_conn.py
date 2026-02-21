import asyncio
import os
from pathlib import Path
import httpx
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# 1. 强制定位并加载配置文件
env_path = Path('.') / '.env.development'
if env_path.exists():
    # override=True 确保强制覆盖当前环境变量
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"✅ 已加载配置文件: {env_path.absolute()}")
else:
    print(f"❌ 找不到配置文件: {env_path.absolute()}")

async def test():
    # --- 调试信息区 ---
    # 明确定义变量，防止 NameError
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    proxy = os.getenv('HTTP_PROXY')

    print(f"\n--- 环境变量读取检查 ---")
    print(f"BINANCE_API_KEY: {'已读取 (前5位: ' + api_key[:5] + ')' if api_key else '❌ 未读取到 (None)'}")
    print(f"BINANCE_API_SECRET: {'已读取' if api_secret else '❌ 未读取到 (None)'}")
    print(f"HTTP_PROXY: {proxy if proxy else '❌ 未读取到 (None)'}")
    print(f"------------------------\n")

    if not api_key or not proxy:
        print("停止测试：请先检查 .env.development 文件中的变量名是否正确，等号两边不要有空格。")
        return

    # --- 代理预检 ---
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=10) as client:
            resp = await client.get("https://www.google.com")
            print(f"✅ 代理测试成功！(Google 状态码: {resp.status_code})")
    except Exception as e:
        print(f"❌ 代理连接失败: {e}")
        return

    # --- 币安连接测试 ---
    params = {
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'proxies': {'http': proxy, 'https': proxy},
        'options': {
            'defaultType': 'future'  # <--- 必须从 'spot' 改为 'future'
        }
    }
    
    # 注意：连接合约演示网时，ccxt 建议直接使用 binance 类的 sandbox
    exchange = ccxt.binance(params)
    exchange.set_sandbox_mode(True) 
    
    try:
        print(f"尝试获取币安测试网余额...")
        balance = await exchange.fetch_balance()
        print(f"✅ 账户连接成功！")
        print(f"USDT 余额: {balance['total'].get('USDT', 0)}")
    except Exception as e:
        print(f"❌ 币安 API 调用失败: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test())