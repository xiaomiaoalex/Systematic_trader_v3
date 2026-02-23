import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Trade:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    leverage: int = 1
    entry_time: datetime = None
    exit_price: float = 0
    exit_time: datetime = None
    pnl: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    strategy: str = ""
    status: str = "OPEN"
    order_id: str = ""
    id: Optional[int] = None

class Database:
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        
        # 👇【核心修复：并发装甲】开启 WAL 模式和 Normal 同步，彻底解决 Database is locked
        await self._conn.execute('PRAGMA journal_mode=WAL;')
        await self._conn.execute('PRAGMA synchronous=NORMAL;')
        
        await self._create_tables()
    
    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
    
    async def _create_tables(self) -> None:
        await self._conn.executescript('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL, side TEXT NOT NULL,
                entry_price REAL NOT NULL, quantity REAL NOT NULL,
                leverage INTEGER DEFAULT 1, entry_time TEXT NOT NULL,
                exit_price REAL DEFAULT 0, exit_time TEXT,
                pnl REAL DEFAULT 0, stop_loss REAL DEFAULT 0,
                take_profit REAL DEFAULT 0, strategy TEXT DEFAULT '',
                status TEXT DEFAULT 'OPEN', order_id TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL, interval TEXT NOT NULL,
                open_time TEXT NOT NULL, open REAL NOT NULL,
                high REAL NOT NULL, low REAL NOT NULL,
                close REAL NOT NULL, volume REAL NOT NULL,
                close_time TEXT NOT NULL,
                UNIQUE(symbol, interval, open_time)
            );
        ''')
        await self._conn.commit()
    
    async def save_trade(self, trade: Trade) -> int:
        cursor = await self._conn.execute('''
            INSERT INTO trades (symbol, side, entry_price, quantity, leverage, entry_time, stop_loss, take_profit, strategy, status, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade.symbol, trade.side, trade.entry_price, trade.quantity, trade.leverage,
              trade.entry_time.isoformat() if trade.entry_time else datetime.now().isoformat(),
              trade.stop_loss, trade.take_profit, trade.strategy, trade.status, trade.order_id))
        await self._conn.commit()
        return cursor.lastrowid
    
    async def update_trade(self, trade_id: int, **kwargs) -> None:
        fields = ', '.join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [trade_id]
        await self._conn.execute(f"UPDATE trades SET {fields} WHERE id = ?", values)
        await self._conn.commit()
    
    async def get_open_trades(self, symbol: Optional[str] = None) -> List[Dict]:
        if symbol:
            cursor = await self._conn.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,))
        else:
            cursor = await self._conn.execute("SELECT * FROM trades WHERE status = 'OPEN'")
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    async def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        cursor = await self._conn.execute("SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    async def save_klines(self, klines: List[Dict]) -> None:
        for k in klines:
            await self._conn.execute('''
                INSERT OR REPLACE INTO klines (symbol, interval, open_time, open, high, low, close, volume, close_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (k['symbol'], k['interval'], k['open_time'], k['open'], k['high'], k['low'], k['close'], k['volume'], k['close_time']))
        await self._conn.commit()
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500) -> List[Dict]:
        cursor = await self._conn.execute(
            "SELECT * FROM klines WHERE symbol = ? AND interval = ? ORDER BY open_time DESC LIMIT ?",
            (symbol, interval, limit)
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in reversed(rows)]

db = Database()
