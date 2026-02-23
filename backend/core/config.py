import os
from abc import ABC, abstractmethod
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

# 👇 ====== 1. 密钥加载抽象层 (Strategy Pattern) ====== 👇
class SecretProvider(ABC):
    """密钥加载器的抽象接口"""
    @abstractmethod
    def get_secret(self, key: str, default: str = "") -> str:
        pass

class EnvSecretProvider(SecretProvider):
    """本地开发/测试环境：从 .env 或环境变量读取"""
    def get_secret(self, key: str, default: str = "") -> str:
        secret = os.getenv(key, default)
        if not secret and "API" in key:
            # 可选：如果你希望本地必须配置密钥，可以在这里打印警告
            pass
        return secret

class CloudSecretManagerProvider(SecretProvider):
    """生产环境：从云端密钥库拉取 (如 AWS/阿里云/K8s Secrets)"""
    def __init__(self):
        # 未来这里可以初始化云厂商的 SDK 客户端
        pass
        
    def get_secret(self, key: str, default: str = "") -> str:
        # TODO: 未来替换为真实的云端请求 API
        # response = client.get_secret_value(SecretId=key)
        # return response['SecretString']
        
        # 暂时回退到环境变量，防止当前直接报错
        print(f"🔒 [安全系统] 生产环境拦截：正在从云端密钥库请求 {key} ...")
        return os.getenv(key, default)

# 👇 ====== 2. 根据环境初始化合适的密钥提供者 ====== 👇
current_env = get_environment()
if current_env == Environment.PRODUCTION:
    secret_provider = CloudSecretManagerProvider()
else:
    secret_provider = EnvSecretProvider()


# 👇 ====== 3. 核心配置对象 ====== 👇
@dataclass
class BinanceConfig:
    # 敏感信息：统一交由 secret_provider 动态获取
    api_key: str = field(default_factory=lambda: secret_provider.get_secret("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: secret_provider.get_secret("BINANCE_API_SECRET", ""))
    use_testnet: bool = field(default_factory=lambda: os.getenv("USE_TESTNET", "true").lower() == "true")
    testnet_api_key: str = field(default_factory=lambda: secret_provider.get_secret("BINANCE_TESTNET_API_KEY", ""))
    testnet_api_secret: str = field(default_factory=lambda: secret_provider.get_secret("BINANCE_TESTNET_API_SECRET", ""))
    
    @property
    def effective_api_key(self) -> str:
        return self.testnet_api_key if self.use_testnet else self.api_key
    
    @property
    def effective_api_secret(self) -> str:
        return self.testnet_api_secret if self.use_testnet else self.api_secret

@dataclass
class TradingConfig:
    # 非敏感信息：继续使用普通的 os.getenv
    # 👇 增加 strip() 自动去除空格，防止配置错误，并转为列表
    symbols: list = field(default_factory=lambda: [
        s.strip() for s in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()
    ])
    kline_interval: str = field(default_factory=lambda: os.getenv("KLINE_INTERVAL", "1h"))
    # 新增：最大同时持仓品种数
    max_active_trades: int = field(default_factory=lambda: int(os.getenv("MAX_ACTIVE_TRADES", "3")))
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
    environment: Environment = field(default_factory=lambda: current_env)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    api: APIConfig = field(default_factory=APIConfig)
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)
    
    def __post_init__(self):
        for d in [self.project_root / "data", self.project_root / "logs"]:
            d.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> None:
        if self.binance.use_testnet and not (self.binance.testnet_api_key and self.binance.testnet_api_secret):
            print("⚠️ 警告: 测试网已启用，但未配置测试网 API 密钥。")
        elif not self.binance.use_testnet and not (self.binance.api_key and self.binance.api_secret):
            print("⚠️ 警告: 实盘已启用，但未配置主网 API 密钥。")

config = Config()