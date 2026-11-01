# Binance U 本位合约自动下单机器人（本地草稿）

本机可跑的 **USDT-M 永续** 策略骨架：拉 K 线 → 算信号 → **默认 dry-run 打印订单意图**。  
默认连接 **Binance Futures Testnet**；真实盘必须显式把 `BINANCE_TESTNET=false`。  
项目文件位于仓库根目录。

> 风险提示：加密合约有爆仓风险。本仓库是学习/草稿骨架，不是生产交易系统。

## 功能概览

| 模块 | 作用 |
|------|------|
| `bot/config.py` | 从环境变量 / `.env` 读配置；API Key 永不写死 |
| `bot/exchange.py` | `ccxt.binanceusdm` 封装（K 线、余额、市价单） |
| `bot/strategy.py` | `ma_crossover`（双均线金叉/死叉）+ `breakout`（N 棒高低突破） |
| `bot/risk.py` | 仓位上限 / 固定比例止损止盈占位（只算价位，不下条件单） |
| `bot/runner.py` | 单次 tick 或循环轮询 |
| `main.py` | CLI 入口 |

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```env
BINANCE_API_KEY=你的testnet_key
BINANCE_API_SECRET=你的testnet_secret
BINANCE_TESTNET=true
SYMBOL=BTC/USDT:USDT
TIMEFRAME=15m
STRATEGY=ma_crossover
```

Testnet 钥匙申请：<https://testnet.binancefuture.com/>

> **Dry-run 拉公开 K 线可以不填 Key。**  
> `--live` 下单或查余额时必须填 Key。

## 运行

### 1）推荐：单次 dry-run（不下单）

```bash
source .venv/bin/activate
python main.py
# 或指定策略 / 周期
python main.py --strategy breakout --timeframe 5m -v
```

成功时会看到类似：

```text
mode=TESTNET/DRY-RUN strategy=ma_crossover symbol=BTC/USDT:USDT tf=15m
[DRY-RUN] BUY 0.00x BTC/USDT:USDT ~xx USDT @ ... SL=... TP=... | ...
```

若当前无交叉/突破，日志会写 `no order intent (flat or zero size)`，属正常。

### 2）循环 dry-run

```bash
python main.py --loop --iterations 3
```

### 3）Testnet 真实下单（仍默认 testnet）

```bash
# .env 里 BINANCE_TESTNET=true，并填好 testnet API Key
python main.py --live
```

### 4）主网（危险，需显式开关）

```env
BINANCE_TESTNET=false
```

再加 `--live` 才会打到主网。CLI **不会**单独把你切到主网。

## 设计取舍

1. **选 ccxt 而非 python-binance**  
   统一封装、USDT-M（`binanceusdm`）与 `set_sandbox_mode` 文档清晰、维护活跃；后续换所成本低。版本钉在 `requirements.txt`。

2. **默认 Testnet + Dry-run 双保险**  
   - `BINANCE_TESTNET` 缺省 `true`  
   - 不加 `--live` 只打印意图，代码路径里 `create_order` 也会拒绝  

3. **策略只用已收盘 K 线**  
   丢掉最后一根未收盘 candle，避免假信号抖动。

4. **风控先占位**  
   `RiskManager` 只算数量与 SL/TP 价位，**不挂**交易所条件单；方便下一步接 `STOP_MARKET` / 仓位状态机。

5. **符号用 ccxt 格式**  
   `BTC/USDT:USDT` = U 本位永续，避免现货/交割混淆。

## 下一步可扩展

- [ ] 仓位状态机（已有多/空时只允许平仓或反手）
- [ ] 交易所原生止损/止盈单（`STOP_MARKET` / `TAKE_PROFIT_MARKET`）
- [ ] 杠杆与保证金模式设置（`set_leverage` / `set_margin_mode`）
- [ ] WebSocket 行情（降低 REST 轮询延迟）
- [ ] 回测与纸面成交日志（CSV / SQLite）
- [ ] 通知（Telegram / 本地推送）与熔断（单日亏损上限）
- [ ] 单元测试：用固定 OHLCV fixture 测交叉/突破

## 目录树

```text
.
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py
└── bot/
    ├── __init__.py
    ├── config.py
    ├── exchange.py
    ├── strategy.py
    ├── risk.py
    └── runner.py
```

## 免责声明

本项目仅供学习与本地实验。使用真实资金造成的任何损失由操作者自行承担。
