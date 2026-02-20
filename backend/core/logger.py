import logging
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
    file = logging.FileHandler(f"logs/trading_{datetime.now().strftime('%Y%m%d')}.log")
    file.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))
    logger.addHandler(file)
    
    return logger

logger = setup_logger()

def get_trade_logger() -> logging.Logger:
    trade_logger = logging.getLogger("trading.trades")
    trade_logger.setLevel(logging.INFO)
    if not trade_logger.handlers:
        Path("logs").mkdir(exist_ok=True)
        handler = logging.FileHandler(f"logs/trades_{datetime.now().strftime('%Y%m%d')}.log")
        handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
        trade_logger.addHandler(handler)
    return trade_logger
