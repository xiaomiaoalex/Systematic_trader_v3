from typing import Optional, List
import pandas as pd
from data.sources.base import Kline
from core.database import db
from core.logger import logger

class KlineStorage:
    def __init__(self, symbol: str, interval: str, max_cache_size: int = 2000):
        self.symbol = symbol
        self.interval = interval
        self.max_cache_size = max_cache_size
        self._klines: List[Kline] = []
        self._df: Optional[pd.DataFrame] = None
    
    async def initialize(self) -> None:
        cached = await db.get_klines(self.symbol, self.interval, self.max_cache_size)
        if cached:
            self._klines = [Kline.from_dict(k) for k in cached]
            self._update_dataframe()
            logger.info(f"[KlineStorage] 加载 {len(self._klines)} 根K线")
    
    async def add_klines(self, klines: List[Kline]) -> int:
        if klines is None or klines.empty: return 0
        existing = {k.open_time for k in self._klines}
# 👇 ====== 高性能 DataFrame 兼容桥梁 (终极形态) ====== 👇
        import pandas as pd

        class DataFrameKlineAdapter:
            """完美的鸭子类型适配器，并解决 SQLite 数据类型不兼容问题"""
            def __init__(self, data_dict):
                clean_dict = {}
                for key, value in data_dict.items():
                    # 核心净化：把 Pandas 的 Timestamp 彻底转换为普通的 Python 整数（毫秒）
                    if isinstance(value, pd.Timestamp):
                        clean_dict[key] = int(value.timestamp() * 1000)
                    else:
                        clean_dict[key] = value
                self.__dict__.update(clean_dict)
            
            def to_dict(self):
                return self.__dict__

        new_klines = []
        if isinstance(klines, pd.DataFrame):
            # 将索引还原为普通列以便读取
            df_temp = klines.reset_index() if klines.index.name else klines
            
            for _, row in df_temp.iterrows():
                time_val = row.get('timestamp', row.get('open_time'))
                if time_val not in existing:
                    row_dict = row.to_dict()
                    row_dict['open_time'] = time_val
                    # 通过净化器实例化
                    new_klines.append(DataFrameKlineAdapter(row_dict))
        else:
            # 保留对原有列表类型的兼容
            new_klines = [k for k in klines if getattr(k, 'open_time', None) not in existing]
        # 👆 ================================================ 👆

        if new_klines:
            self._klines.extend(new_klines)
            if len(self._klines) > self.max_cache_size:
                self._klines = self._klines[-self.max_cache_size:]
            await db.save_klines([k.to_dict() for k in new_klines])
            self._update_dataframe()
        return len(new_klines)
    
    def _update_dataframe(self) -> None:
        if not self._klines:
            self._df = pd.DataFrame()
            return
        data = [{'open_time': k.open_time, 'open': k.open, 'high': k.high, 'low': k.low,
                'close': k.close, 'volume': k.volume} for k in self._klines]
        self._df = pd.DataFrame(data)
        self._df.set_index('open_time', inplace=True)
    
    def get_dataframe(self, limit: Optional[int] = None) -> pd.DataFrame:
        if self._df is None or self._df.empty: return pd.DataFrame()
        return self._df.tail(limit).copy() if limit else self._df.copy()
    
    @property
    def current_price(self) -> float:
        return self._klines[-1].close if self._klines else 0.0
