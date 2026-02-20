"""
加密货币数据源
基于CCXT实现，支持多个交易所
"""
import os
from typing import Optional, List, Dict
from datetime import datetime
import ccxt.async_support as ccxt

from data.sources.base import Kline, Ticker
from core.config import config
from core.logger import logger
from core.exceptions import DataError


class CryptoDataSource:
    """加密货币数据源"""
    
    TIMEFRAME_MAP = {
        '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m',
        '30m': '30m', '1h': '1h', '2h': '2h', '4h': '4h',
        '6h': '6h', '12h': '12h', '1d': '1d', '1w': '1w', '1M': '1M'
    }
    
    TIMEFRAME_MS = {
        '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000,
        '30m': 1800000, '1h': 3600000, '2h': 7200000, '4h': 14400000,
        '6h': 21600000, '12h': 43200000, '1d': 86400000, '1w': 604800000
    }
    
    def __init__(self, exchange_id: str = 'binance'):
        self.name = exchange_id
        self._exchange: Optional[ccxt.Exchange] = None
        self._connected = False
        self._http_proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
    
    @staticmethod
    def _to_ccxt_symbol(symbol: str) -> str:
        if '/' in symbol:
            return symbol
        for quote in ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB']:
            if symbol.endswith(quote):
                return f"{symbol[:-len(quote)]}/{quote}"
        return symbol
    
    @staticmethod
    def _to_standard_symbol(symbol: str) -> str:
        return symbol.replace('/', '')
    
    async def connect(self) -> None:
        try:
            exchange_config = {
                'apiKey': config.binance.effective_api_key,
                'secret': config.binance.effective_api_secret,
                'enableRateLimit': True,
                'options': {
                    'adjustForTimeDifference': True,
                }
            }
            
            if self._http_proxy:
                exchange_config['aiohttp_proxy'] = self._http_proxy
                logger.info(f"[{self.name}] 使用代理")
            
            # 测试网配置 - 直接设置URL
            if config.binance.use_testnet:
                exchange_config['options']['defaultType'] = 'future'
                logger.info(f"[{self.name}] 使用测试网环境")
            
            self._exchange = ccxt.binance(exchange_config)
            await self._exchange.load_markets()
            
            self._connected = True
            logger.info(f"[{self.name}] 连接成功")
            
        except Exception as e:
            self._connected = False
            logger.error(f"[{self.name}] 连接失败: {e}")
            raise DataError(f"连接交易所失败: {e}")
    
    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        self._connected = False
        logger.info(f"[{self.name}] 已断开连接")
    
    async def get_klines(self, symbol: str, interval: str = '1h', limit: int = 500,
                         start_time: Optional[int] = None) -> List[Kline]:
        if not self._connected:
            raise DataError("数据源未连接")
        
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        timeframe = self.TIMEFRAME_MAP.get(interval, '1h')
        
        try:
            ohlcv = await self._exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=limit)
            interval_ms = self.TIMEFRAME_MS.get(timeframe, 3600000)
            
            return [Kline(
                symbol=symbol, interval=interval,
                open_time=datetime.fromtimestamp(item[0] / 1000),
                open=float(item[1]), high=float(item[2]), low=float(item[3]),
                close=float(item[4]), volume=float(item[5]),
                close_time=datetime.fromtimestamp((item[0] + interval_ms) / 1000)
            ) for item in ohlcv]
        except Exception as e:
            logger.error(f"获取K线失败: {e}")
            raise DataError(f"获取K线数据失败: {e}")
    
    async def get_ticker(self, symbol: str) -> Ticker:
        if not self._connected:
            raise DataError("数据源未连接")
        
        ticker = await self._exchange.fetch_ticker(self._to_ccxt_symbol(symbol))
        return Ticker(
            symbol=symbol, last=float(ticker['last']),
            bid=float(ticker.get('bid', 0)), ask=float(ticker.get('ask', 0)),
            high_24h=float(ticker.get('high', 0)), low_24h=float(ticker.get('low', 0)),
            volume_24h=float(ticker.get('baseVolume', 0))
        )
    
    async def get_symbols(self) -> List[str]:
        if not self._connected:
            raise DataError("数据源未连接")
        return [self._to_standard_symbol(s) for s in self._exchange.markets.keys() if '/USDT' in s]
    
    async def get_balance(self, asset: str = 'USDT') -> float:
        if not self._connected:
            raise DataError("数据源未连接")
        balance = await self._exchange.fetch_balance()
        return float(balance.get(asset, {}).get('total', 0))
    
    async def get_account_info(self) -> Dict:
        if not self._connected:
            raise DataError("数据源未连接")
        balance = await self._exchange.fetch_balance()
        return {
            'totalWalletBalance': balance.get('USDT', {}).get('total', 0),
            'availableBalance': balance.get('USDT', {}).get('free', 0),
            'assets': [{'asset': a, 'walletBalance': i.get('total', 0)}
                      for a, i in balance.items() if isinstance(i, dict) and i.get('total', 0) > 0]
        }
    
    async def get_positions(self) -> List[Dict]:
        if not self._connected:
            raise DataError("数据源未连接")
        balance = await self._exchange.fetch_balance()
        return [{'symbol': f"{a}USDT", 'asset': a, 'quantity': float(i.get('total', 0)), 'side': 'LONG'}
               for a, i in balance.items() if isinstance(i, dict) and float(i.get('total', 0)) > 0
               and a not in ['USDT', 'BUSD', 'USDC']]
    
    async def place_order(self, symbol: str, side: str, order_type: str,
                         quantity: float, price: Optional[float] = None) -> Dict:
        if not self._connected:
            raise DataError("数据源未连接")
        
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        ccxt_side = 'buy' if side.upper() == 'BUY' else 'sell'
        
        if order_type.upper() == 'MARKET':
            order = await self._exchange.create_market_order(ccxt_symbol, ccxt_side, quantity)
        else:
            order = await self._exchange.create_limit_order(ccxt_symbol, ccxt_side, quantity, price)
        
        return {
            'orderId': order.get('id'), 'symbol': symbol, 'status': order.get('status'),
            'filled': float(order.get('filled', 0)), 'average': float(order.get('average', 0) or 0)
        }
    
    @property
    def is_connected(self) -> bool:
        return self._connected


crypto_data_source = CryptoDataSource()
