# Function Calling 与 MCP

基于 Qwen-Agent（DashScope 通义千问）的 Function Calling 与 MCP 项目：两组示例应用 + 两个业务场景。

## 项目结构

```
function-calling-and-mcp/
├── case-function-calling/          门票助手，Function Calling 三版演进
│   ├── assistant_ticket_bot-1.py  v1 纯 SQL 查询，返回 Markdown 表格
│   ├── assistant_ticket_bot-2.py  v2 查询结果自动出柱状图
│   ├── assistant_ticket_bot-3.py  v3 绘图重构 + 接入高德地图 / Tavily 两个 MCP
│   └── assistant_ticket_bot_logic.html   v1 代码逻辑图解（浏览器直接打开）
├── case-mcp/                       MCP 助手集合
│   ├── assistant_mcp_amap_bot.py  高德地图助手（旅行规划、地点查询、路线导航）
│   ├── assistant_mcp_tavily_bot.py    联网搜索助手（搜索、新闻、网页提取）
│   ├── assistant_mcp_txt_bot.py   本地文件助手（统计桌面 txt 文件）
│   ├── txt_counter.py             自研 FastMCP Server（统计/列出/读取桌面 txt）
│   └── 旅行规划.md                 A4 可打印 HTML 行程表提示词模板
├── exercise1-sales-assistant/      销售业务助手（Function Calling + SQLite）
│   ├── seed_sales_data.py         生成 sales.db 示例数据
│   └── sales_assistant.py         业务助手本体
└── exercise2-agent-mcp/            Agent + MCP 应用
    └── cursor-mcp.json            Cursor 客户端的 MCP 服务配置
```

## 环境准备

1. 安装依赖（Python 3.11、Node.js 18+，MCP 服务通过 npx 启动）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 配置密钥与环境变量。复制 `.env.example` 为 `.env` 后填入自己的 key：

```bash
cp .env.example .env
```

`.env` 已被 git 忽略，**key 只能写进 `.env`，不要写进会被提交的 `.env.example`**。

脚本只读取进程环境变量，不会自动加载 `.env`，填完必须导入当前终端（macOS / Linux）：

```bash
set -a; source .env; set +a
```

Windows PowerShell：

```powershell
Get-Content .env | ForEach-Object { if ($_ -and $_ -notmatch '^#') { $p = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($p[0], $p[1], 'Process') } }
```

也可以不用 `.env`，直接逐个导出（macOS / Linux）：

```bash
export DASHSCOPE_API_KEY=你的key
export TAVILY_API_KEY=你的key
export AMAP_MAPS_API_KEY=你的key
```

3. 模型与额度：可运行的助手默认用 `qwen3.8-27b`，并走百炼的 OpenAI 兼容通道（`https://dashscope.aliyuncs.com/compatible-mode/v1`），因为原生 DashScope 通道不支持该模型。免费额度有限且有到期时间，用尽或过期后到百炼控制台查看仍有额度的模型（如 `qwen3.8-flash`、`kimi-k3`），把脚本 `llm_cfg` 里的 `model` 换掉即可。

密钥申请入口：

| 环境变量 | 用途 | 申请入口 |
|---|---|---|
| DASHSCOPE_API_KEY | 通义千问 / 百炼上的模型（必填，所有脚本都要用） | 阿里云百炼控制台 API-KEY 管理 |
| TAVILY_API_KEY | Tavily 搜索 MCP（有免费额度） | https://app.tavily.com 注册后在控制台获取 |
| AMAP_MAPS_API_KEY | 高德地图 MCP（免费，服务平台选「Web服务」） | https://console.amap.com 创建应用后添加 Key |
| MYSQL_* | 门票助手使用的数据库 | 换成自己的 MySQL 即可，销售业务助手不需要 |

高德 Key 申请步骤（免费，需登录本人的高德账号，无法由他人代办）：

1. 打开 https://console.amap.com 并登录
2. 进入「应用管理 → 我的应用」，点「创建新应用」，填应用名称与类型
3. 在新建的应用下点「添加 Key」，**服务平台必须选「Web服务」**，选错会导致地图 MCP 调用被拒绝
4. 提交后复制生成的 Key，填入 `.env` 的 `AMAP_MAPS_API_KEY`

## Function Calling 门票助手

三个版本是同一功能的逐步演进，任选一个运行即可（浏览器会打开 Gradio 界面）：

```bash
python case-function-calling/assistant_ticket_bot-1.py   # 纯查表
python case-function-calling/assistant_ticket_bot-2.py   # 查表 + 自动出图
python case-function-calling/assistant_ticket_bot-3.py   # 查表 + 出图 + MCP
```

依赖一张 MySQL 门票订单表 `tkt_orders`，连接信息通过 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` 五个环境变量配置。`assistant_ticket_bot_logic.html` 是 v1 的调用流程图解。

## MCP 助手

```bash
cd case-mcp
python assistant_mcp_amap_bot.py      # 需要 AMAP_MAPS_API_KEY
python assistant_mcp_tavily_bot.py    # 需要 TAVILY_API_KEY
python assistant_mcp_txt_bot.py       # 本地服务，无需密钥
```

必须在 `case-mcp` 目录下启动：`assistant_mcp_txt_bot.py` 的 MCP 配置用相对路径 `python txt_counter.py`，换目录会找不到脚本。

## 销售业务助手（Function Calling）

用自然语言查询销售数据，覆盖四类典型业务问题：

1. 查询某个月的销量是多少？
2. 对比查询这个月比上个月销量的增长是多少？
3. 查询不同省份的销售额是多少？
4. 查询某一个时间段内，销售金额最多的前 3 个渠道是？

运行步骤：

```bash
source .venv/bin/activate
python exercise1-sales-assistant/seed_sales_data.py    # 生成 sales.db（595 行示例数据）
python exercise1-sales-assistant/sales_assistant.py    # 启动 Web 界面
```

界面已预置四个示例问题，也可以直接问：

- 2026年10月的销量是多少？
- 2026年10月相比9月的销量增长了多少？
- 2026年7月到9月不同省份的销售额是多少？
- 2026年7月1日到9月30日，销售金额最多的前3个渠道是哪些？

数据说明：示例数据覆盖 2026-05 至 2026-10 共 6 个月、8 个省份（广东、江苏、浙江、山东、四川、湖北、北京、上海）、5 个渠道（线上直营、电商平台、经销商、直播带货、线下门店），随机种子固定为 42，重复生成结果一致。

实现要点：助手通过 `exc_sql` 工具把模型生成的 SQL 打到本地 SQLite，运行环境是 SQLite 而非 MySQL，月份必须用 `strftime('%Y-%m', sale_date)`，不能用 `MONTH()` 或 `DATE_FORMAT()`，这一点已写进 system prompt。

## Agent + MCP 应用

四个任务与对应能力：

| 任务 | 使用的 MCP 服务 | 建议提问 |
|---|---|---|
| 规划 7 天自驾游 | amap-maps | 帮我规划一条从成都出发的 7 天自驾游路线，给出每天的城市、景点、驾车里程和住宿建议 |
| 网页内容转 Markdown | tavily-mcp | 获取 https://example.com 的网页内容，并转换成 Markdown 格式输出 |
| 检索最新关税新闻 | tavily-mcp | 检索最近一周关于关税的最新新闻，列出标题、来源、时间和链接 |
| 统计桌面 txt 文件数量 | txt-counter | 统计一下我桌面上有多少个 txt 文件，并把文件名列出来 |

方式一：用 Qwen-Agent 代码（仓库内已具备，零额外代码）

```bash
cd case-mcp
python assistant_mcp_amap_bot.py      # 任务1
python assistant_mcp_tavily_bot.py    # 任务2、任务3
python assistant_mcp_txt_bot.py       # 任务4
```

说明：

- 任务4 统计的是 `~/Desktop` 下的 `.txt` 文件，桌面没有 txt 时会返回 0 个，演示前可先在桌面放几个 txt 文件。
- 三个 MCP 里只有 `txt-counter` 是本地服务，它由 `assistant_mcp_txt_bot.py` 用当前解释器（`sys.executable`）启动。系统自带 python 的 `mcp` 版本与 `txt_counter.py` 不兼容，直接用会导致 MCP 连接失败，因此请统一用仓库 `.venv` 里的 python 运行脚本。

方式二：用 Cursor 客户端

把 `exercise2-agent-mcp/cursor-mcp.json` 里的内容填入 `~/.cursor/mcp.json`（全局生效）或项目目录下的 `.cursor/mcp.json`，把两个 key 换成自己的，重启 Cursor 后在 Agent 模式直接用自然语言提问即可。配置里 npx 与 python 都写了绝对路径，避免客户端读不到命令行环境。

## 常见问题

- 提示 `Free quota exhausted`：当前模型的免费额度已用完或已过期。到百炼控制台「模型额度」页挑一个仍有额度的模型（如 `qwen3.8-flash`、`kimi-k3`），把脚本 `llm_cfg` 里的 `model` 换成它；也可以充值或关闭「仅使用免费额度」开关。
- 提示 `url error, please check url`：说明该模型不支持原生 DashScope 通道，按上面「模型与额度」的说明改用 OpenAI 兼容通道（`model_server`）。
- 提示 `The dependencies for GUI support are not installed`：执行 `pip install "qwen-agent[gui]"`，若仍报缺少 `soundfile`，再执行 `pip install soundfile`。
- txt-counter MCP 报 `Connection closed`：脚本被系统 python 拉起而它的 `mcp` 版本不兼容，请用仓库 `.venv` 里的 python 运行 `assistant_mcp_txt_bot.py`。
- pip 卸载旧包被拦截：建议在仓库内新建虚拟环境安装（见环境准备），不要在全局环境反复升降级。
- 想看门票助手的 SQL 执行过程：打开终端时把脚本里的 `app_gui()` 改成 `app_tui()`，可在命令行直接对话。
