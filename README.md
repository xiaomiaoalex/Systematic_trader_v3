# 币安自动交易系统 v3.0

一个专业级的加密货币自动交易系统，支持策略回测、风险管理和Web界面。

## ✨ 特性

- 🎯 **策略系统** - 模块化策略架构，易于扩展
- 📊 **回测引擎** - 完整的回测系统，支持多指标分析
- ⚠️ **风险管理** - 多维度风险控制
- 🖥️ **Web界面** - 现代化的管理界面
- 🐳 **Docker支持** - 一键部署

## 📁 目录结构

```
trading_system_final/
├── backend/                 # 后端代码
│   ├── core/               # 核心模块
│   ├── data/               # 数据层
│   ├── strategies/         # 策略层
│   ├── risk/               # 风险管理
│   ├── execution/          # 执行层
│   ├── backtest/           # 回测系统
│   ├── api/                # API层
│   ├── main.py             # 主程序
│   └── requirements.txt    # 依赖
│
├── frontend/               # 前端代码
│   └── src/
│       ├── index.html
│       ├── css/
│       └── js/
│
├── deploy/                 # 部署配置
│   ├── docker-compose.yml
│   └── nginx.conf
│
├── scripts/                # 脚本
│   └── start.sh
│
└── docs/                   # 文档
```

## 🚀 快速开始

### 方式一：直接运行

运行说明：

在 backend/ 下创建 .env 并配置 API 密钥。

Windows 用户推荐运行 scripts/run.ps1 以获得 AboveNormal 进程优先级。


```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入API密钥

# 3. 启动后端
python main.py

# 4. 启动前端（新终端）
cd frontend/src
python -m http.server 3000
```

### 方式二：Docker部署

```bash
# 使用docker-compose
cd deploy
docker-compose up -d
```

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| ENVIRONMENT | 运行环境 | development |
| USE_TESTNET | 使用测试网 | true |
| SYMBOL | 交易对 | BTCUSDT |
| MAX_POSITION_PERCENT | 最大仓位比例 | 10 |
| MAX_DAILY_LOSS_PERCENT | 日亏损限制 | 5.0 |

## 📖 API文档

启动后访问：http://localhost:8080/docs

### 主要接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/account | GET | 获取账户信息 |
| /api/positions | GET | 获取持仓 |
| /api/strategies | GET | 获取策略列表 |
| /api/backtest/run | POST | 运行回测 |
| /api/risk/status | GET | 获取风险状态 |

## 🎯 策略开发

```python
from strategies.base import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    NAME = "my_strategy"
    DESCRIPTION = "我的策略"
    
    async def generate_signal(self, df, position):
        # 实现策略逻辑
        if condition:
            return Signal(
                strategy_name=self.NAME,
                signal_type=SignalType.BUY,
                symbol="BTCUSDT",
                price=current_price
            )
        return None
```

## ⚠️ 风险提示

- 本系统仅供学习和研究使用
- 加密货币交易存在高风险
- 请使用测试网进行测试
- 实盘交易请谨慎

## 📄 许可证

MIT License
