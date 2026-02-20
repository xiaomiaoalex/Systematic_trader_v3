import os
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

class Environment(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

def get_environment() -> Environment:
    env = os.getenv("ENVIRONMENT", "development").lower()
    return Environment(env)

@dataclass
class BinanceConfig:
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    use_testnet: bool = field(default_factory=lambda: os.getenv("USE_TESTNET", "true").lower() == "true")
    testnet_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_KEY", ""))
    testnet_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_SECRET", ""))
    
    @property
    def effective_api_key(self) -> str:
        return self.testnet_api_key if self.use_testnet else self.api_key
    
    @property
    def effective_api_secret(self) -> str:
        return self.testnet_api_secret if self.use_testnet else self.api_secret

@dataclass
class TradingConfig:
    symbol: str = field(default_factory=lambda: os.getenv("SYMBOL", "BTCUSDT"))
    kline_interval: str = field(default_factory=lambda: os.getenv("KLINE_INTERVAL", "1h"))
    max_position_percent: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_PERCENT", "10")))
    max_daily_loss_percent: float = field(default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS_PERCENT", "5.0")))
    max_drawdown_percent: float = field(default_factory=lambda: float(os.getenv("MAX_DRAWDOWN_PERCENT", "15.0")))

@dataclass
class APIConfig:
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8080")))
    cors_origins: list = field(default_factory=lambda: ["*"])

@dataclass
class Config:
    environment: Environment = field(default_factory=get_environment)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    api: APIConfig = field(default_factory=APIConfig)
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)
    
    def __post_init__(self):
        for d in [self.project_root / "data", self.project_root / "logs"]:
            d.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> None:
        pass

config = Config()
