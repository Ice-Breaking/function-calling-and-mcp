"""销售业务助手（Qwen-Agent + Function Calling + SQLite）

运行方式：
    1. python seed_sales_data.py     # 生成 sales.db
    2. python sales_assistant.py     # 启动 Web 界面，用自然语言提问

功能：用自然语言查询销售数据，支持某月销量、环比增长、分省销售额、
某时间段销售金额 Top3 渠道等问题。
"""

import os

import dashscope
import pandas as pd
from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI
from qwen_agent.tools.base import BaseTool, register_tool
from sqlalchemy import create_engine

# 配置 DashScope（API Key 从环境变量读取）
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
dashscope.timeout = 30  # 设置超时时间为 30 秒

# 本地 SQLite 数据库路径，由 seed_sales_data.py 生成
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sales.db')

# 销售额等浮点数列按普通小数显示，避免输出科学计数法（如 1.42e+06）
pd.set_option('display.float_format', '{:,.2f}'.format)

# ====== 销售助手 system prompt ======
system_prompt = """我是销售业务助手，以下是销售订单表 sales 的字段，我会编写对应的SQL(运行环境是SQLite3)，对数据进行查询
-- 销售订单表
CREATE TABLE sales (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date TEXT    NOT NULL,   -- 订单日期 YYYY-MM-DD
    province  TEXT    NOT NULL,   -- 省份
    channel   TEXT    NOT NULL,   -- 销售渠道
    quantity  INTEGER NOT NULL,   -- 销量
    amount    REAL    NOT NULL    -- 销售金额(元)
);
SQLite 语法约定，必须严格遵守，否则 SQL 会执行报错：
1. 取月份用 strftime('%Y-%m', sale_date)，禁止使用 MySQL 的 MONTH() 或 DATE_FORMAT()
2. 取年份用 strftime('%Y', sale_date)
3. 日期区间过滤用 sale_date BETWEEN '2026-07-01' AND '2026-09-30'
4. 环比增长：先按 strftime('%Y-%m', sale_date) 分组统计每月销量或金额，再用自连接或 LAG() 窗口函数与上一月对比，增长率用 (本月-上月)*100.0/上月
5. 取前 N 名用 ORDER BY ... DESC LIMIT N
数据范围：2026-05 至 2026-10 共 6 个月；省份包括广东、江苏、浙江、山东、四川、湖北、北京、上海；渠道包括线上直营、电商平台、经销商、直播带货、线下门店。
我将回答用户关于销量、销售额、环比增长、省份分布、渠道排名等业务问题，回答时给出查询结果的 Markdown 表格。
"""

# ====== exc_sql 工具类实现 ======
@register_tool('exc_sql')
class ExcSQLTool(BaseTool):
    """
    SQL查询工具，执行传入的SQL语句并返回Markdown表格。
    """

    description = '对于生成的SQL，进行SQLite查询，并返回Markdown表格'
    parameters = [{
        'name': 'sql_input',
        'type': 'string',
        'description': '生成的SQL语句，必须是SQLite语法',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        import json
        args = json.loads(params)
        sql_input = args['sql_input']
        # 连接本地 SQLite 数据库
        engine = create_engine(f'sqlite:///{DB_PATH}')
        df = pd.read_sql(sql_input, engine)
        # 返回前30行，防止数据过多
        return df.head(30).to_markdown(index=False)


# ====== 初始化销售助手服务 ======
def init_agent_service():
    """初始化销售助手服务"""
    llm_cfg = {
        'model': 'qwen-plus',
        'timeout': 30,
        'retry_count': 3,
    }
    try:
        bot = Assistant(
            llm=llm_cfg,
            name='销售业务助手',
            description='销售数据查询与分析',
            system_message=system_prompt,
            function_list=['exc_sql'],
        )
        print('助手初始化成功！')
        return bot
    except Exception as e:
        print(f'助手初始化失败: {str(e)}')
        raise


def app_tui():
    """终端交互模式

    提供命令行交互界面，支持：
    - 连续对话
    - 文件输入
    - 实时响应
    """
    try:
        # 初始化助手
        bot = init_agent_service()

        # 对话历史
        messages = []
        while True:
            try:
                # 获取用户输入
                query = input('user question: ')
                # 获取可选的文件输入
                file = input('file url (press enter if no file): ').strip()

                # 输入验证
                if not query:
                    print('user question cannot be empty！')
                    continue

                # 构建消息
                if not file:
                    messages.append({'role': 'user', 'content': query})
                else:
                    messages.append({'role': 'user', 'content': [{'text': query}, {'file': file}]})

                print('正在处理您的请求...')
                # 运行助手并处理响应
                response = []
                for response in bot.run(messages):
                    print('bot response:', response)
                messages.extend(response)
            except Exception as e:
                print(f'处理请求时出错: {str(e)}')
                print('请重试或输入新的问题')
    except Exception as e:
        print(f'启动终端模式失败: {str(e)}')


def app_gui():
    """图形界面模式，提供 Web 图形界面"""
    try:
        print('正在启动 Web 界面...')
        # 初始化助手
        bot = init_agent_service()
        # 配置聊天界面，列出四类典型业务问题
        chatbot_config = {
            'prompt.suggestions': [
                '2026年10月的销量是多少？',
                '2026年10月相比9月的销量增长了多少？',
                '2026年7月到9月不同省份的销售额是多少？',
                '2026年7月1日到9月30日，销售金额最多的前3个渠道是哪些？',
            ]
        }
        print('Web 界面准备就绪，正在启动服务...')
        # 启动 Web 界面
        WebUI(
            bot,
            chatbot_config=chatbot_config
        ).run()
    except Exception as e:
        print(f'启动 Web 界面失败: {str(e)}')
        print('请检查网络连接和 API Key 配置')


if __name__ == '__main__':
    # 运行模式选择
    app_gui()          # 图形界面模式（默认）
