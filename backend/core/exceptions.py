class TradingSystemError(Exception):
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        super().__init__(self.message)

class ConfigError(TradingSystemError):
    def __init__(self, message: str):
        super().__init__(message, "CONFIG_ERROR")

class DataError(TradingSystemError):
    def __init__(self, message: str):
        super().__init__(message, "DATA_ERROR")

class StrategyError(TradingSystemError):
    def __init__(self, message: str):
        super().__init__(message, "STRATEGY_ERROR")

class ExecutionError(TradingSystemError):
    def __init__(self, message: str):
        super().__init__(message, "EXECUTION_ERROR")

class RiskError(TradingSystemError):
    def __init__(self, message: str):
        super().__init__(message, "RISK_ERROR")
