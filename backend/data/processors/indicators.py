import pandas as pd
import numpy as np

class TechnicalIndicators:
    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = self.add_ma(df)
        df = self.add_bollinger(df)
        df = self.add_rsi(df)
        df = self.add_macd(df)
        df = self.add_atr(df)
        df = self.add_volume_indicators(df)
        return df
    
    def add_ma(self, df: pd.DataFrame) -> pd.DataFrame:
        for period in [7, 20, 50, 100, 200]:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
            df[f'ema{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        return df
    
    def add_bollinger(self, df: pd.DataFrame) -> pd.DataFrame:
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
        return df
    
    def add_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        df['macd'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        return df
    
    def add_atr(self, df: pd.DataFrame) -> pd.DataFrame:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()
        return df
    
    def add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        return df

indicators = TechnicalIndicators()
