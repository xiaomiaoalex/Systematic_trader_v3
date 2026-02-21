import asyncio
import logging
import ccxt.async_support as ccxt
from typing import Dict, List, Optional, Any
import pandas as pd

from core.config import config
from core.exceptions import DataError

logger = logging.getLogger(__name__)

class CryptoDataSource:
    """加密货币数据源 (支持 Binance 实盘与模拟盘)"""
    
    def __init__(self):
        self.name = "binance"
        self._exchange: Optional[ccxt.binance] = None
        self._connected = False

    async def connect(self) -> None:
        """建立与交易所的异步连接"""
        try:
            # 基础配置
            exchange_config = {
                'apiKey': config.binance.effective_api_key,
                'secret': config.binance.effective_api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',         # 明确交易类型为合约
                    'adjustForTimeDifference': True, # 自动同步系统时间防止签名错误
                }
            }
            
            # 👇 ====== 强制开启本地网络代理 ====== 👇
            local_proxy = "http://127.0.0.1:4780"
            
            exchange_config['proxies'] = {
                'http': local_proxy,
                'https': local_proxy
            }
            exchange_config['aiohttp_proxy'] = local_proxy  # 确保异步引擎穿透
            
            logger.info(f"[{self.name}] 强制网络代理已开启: {local_proxy}")
            # 👆 ========================================= 👆
            
            # 实例化 CCXT
            self._exchange = ccxt.binance(exchange_config)
            
            # --- 核心：CCXT 最新版 Demo Trading 专属开关 ---
            # 使用 getattr 防御性读取，防止 config 中缺少 use_testnet 属性报错
            if getattr(config.binance, 'use_testnet', False):
                self._exchange.enable_demo_trading(True)
                logger.info(f"[{self.name}] 已开启币安 Demo Trading (模拟交易) 环境")
            
            # 验证连接并预载市场信息
            await self._exchange.load_markets()
            
            self._connected = True
            logger.info(f"[{self.name}] 连接成功")
            
        except Exception as e:
            self._connected = False
            logger.error(f"[{self.name}] 连接失败: {e}")
            raise DataError(f"连接交易所失败: {e}")

    async def close(self) -> None:
        """关闭交易所连接"""
        if self._exchange:
            await self._exchange.close()
            self._connected = False
            logger.info(f"[{self.name}] 已断开连接")

    async def fetch_ohlcv(
        self, 
        symbol: str, 
        timeframe: str = '1m', 
        limit: int = 500,
        max_retries: int = 3  # 👇 新增：最大重试次数
    ) -> pd.DataFrame:
        """
        获取历史 K 线数据 (自带网络防弹与指数退避重试机制)
        """
        # 开启重试循环
        for attempt in range(max_retries):
            try:
                if not self._connected or not self._exchange:
                    await self.connect()
                    
                # 统一符号格式
                formatted_symbol = symbol.replace('/', '')
                
                # 发起网络请求
                ohlcv = await self._exchange.fetch_ohlcv(
                    formatted_symbol, 
                    timeframe=timeframe, 
                    limit=limit
                )
                
                if not ohlcv:
                    return pd.DataFrame()
                    
                df = pd.DataFrame(
                    ohlcv, 
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # 注入数据库需要的身份信息
                df['symbol'] = symbol
                df['interval'] = timeframe
                df['open_time'] = df['timestamp']
                df['close_time'] = df['timestamp']
                
                # 转换时间戳为 datetime 对象并设为索引
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                
                return df
                
            # 👇 ====== 核心防弹衣：网络异常精确捕获 ====== 👇
            except ccxt.NetworkError as e:
                # 触发指数退避：1秒 -> 2秒 -> 4秒
                wait_time = 2 ** attempt  
                logger.warning(f"[{self.name}] ⚠️ 网络波动，拉取K线失败: {e}。等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                await asyncio.sleep(wait_time)
                
            except ccxt.ExchangeError as e:
                # 触发交易所业务报错（比如 API Key 过期、参数写错），重试没用，直接打断
                logger.error(f"[{self.name}] ❌ 交易所拒绝请求: {e}")
                break
                
            except Exception as e:
                # 触发其他致命错误
                logger.exception(f"[{self.name}] 💥 获取 K 线发生未知致命错误:")
                break
            # 👆 ========================================= 👆

        # 如果循环结束还没 return，说明重试耗尽了
        logger.error(f"[{self.name}] 🚨 达到最大重试次数 ({max_retries})，获取 K 线彻底失败 ({symbol})")
        return pd.DataFrame()
        
    # 👇 ====== 查账接口 ====== 👇
    async def get_account_info(self) -> dict:
        """获取账户当前的钱包余额信息"""
        if not self._connected or not self._exchange:
            await self.connect()
            
        try:
            # 调用 CCXT 原生的 fetch_balance 获取资产字典
            balance = await self._exchange.fetch_balance()
            return balance
            
        except Exception as e:
            logger.error(f"[{self.name}] ❌ 获取账户余额失败: {e}")
            return {}
    

    async def fetch_balance(self) -> Dict[str, Any]:
        """获取账户余额 (仅限合约账户)"""
        if not self._connected or not self._exchange:
            await self.connect()
            
        try:
            balance = await self._exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"[{self.name}] 获取余额失败: {e}")
            return {}
    
    # 👇 ====== 新增的兼容桥梁 ====== 👇
    async def disconnect(self) -> None:
        """兼容其他模块的 disconnect 调用"""
        await self.close()

    async def get_balance(self) -> Dict[str, Any]:
        """兼容其他模块的 get_balance 调用"""
        return await self.fetch_balance()
    # 👆 ============================ 👆
    # 👇 ====== 这是要新增的最后一块拼图 ====== 👇
    async def get_klines(self, symbol: str, interval: str = '1m', limit: int = 500, **kwargs) -> pd.DataFrame:
        """兼容其他模块获取K线的调用 (将 interval 映射到 timeframe)"""
        # 如果有传来 timeframe 就用 timeframe，否则默认用 interval
        timeframe = kwargs.get('timeframe', interval)
        return await self.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    @property
    def is_connected(self) -> bool:
        return self._connected
    
    @property
    def is_connected(self) -> bool:
        return self._connected

# ==========================================
# 创建全局单例对象，供其他模块直接导入使用
# 解决 ImportError: cannot import name 'crypto_data_source'
# ==========================================
crypto_data_source = CryptoDataSource()