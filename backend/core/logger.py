import logging
from logging.handlers import RotatingFileHandler  # 👈 引入强大的滚动处理器
import sys
from pathlib import Path
from datetime import datetime
import os

class ColoredFormatter(logging.Formatter):
    COLORS = {'DEBUG': '\033[36m', 'INFO': '\033[32m', 'WARNING': '\033[33m', 'ERROR': '\033[31m', 'CRITICAL': '\033[35m'}
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

def setup_logger(name: str = "trading", level: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper()))
    
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColoredFormatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(console)
    
    Path("logs").mkdir(exist_ok=True)
    
    # 👇 核心升级：单文件上限 10MB，最多保留 5 个旧文件 (50MB总容量)，彻底告别文件撑爆
    log_file = f"logs/trading_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        filename=log_file, 
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,              # 保留 5 个备份 (trading_xxx.log.1, .log.2...)
        encoding='utf-8'            # 依然保留刚才修好的 UTF-8 防御
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

def get_trade_logger() -> logging.Logger:
    trade_logger = logging.getLogger("trading.trades")
    trade_logger.setLevel(logging.INFO)
    if not trade_logger.handlers:
        Path("logs").mkdir(exist_ok=True)
        
        # 👇 交易记录也一样，加入滚动切割机制
        log_file = f"logs/trades_{datetime.now().strftime('%Y%m%d')}.log"
        trade_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=5 * 1024 * 1024,  # 交易记录文件较小，设为 5MB 滚动
            backupCount=10,            # 保留更多历史以便对账
            encoding='utf-8'
        )
        trade_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
        trade_logger.addHandler(trade_handler)
        
    return trade_logger