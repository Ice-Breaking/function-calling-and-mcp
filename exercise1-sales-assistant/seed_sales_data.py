"""生成销售示例数据到本地 SQLite 数据库 sales.db

运行方式：
    python seed_sales_data.py

脚本会在当前目录生成（并重置）sales.db，写入 2026-05 至 2026-10 共 6 个月、
8 个省份、5 个渠道的销售订单数据，供 sales_assistant.py 查询。
"""

import calendar
import os
import random
import sqlite3

# 数据库文件与脚本放在同一目录（.gitignore 已排除 *.db）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sales.db')

# 数据覆盖的月份
MONTHS = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10']

# 省份与销售渠道
PROVINCES = ['广东', '江苏', '浙江', '山东', '四川', '湖北', '北京', '上海']
CHANNELS = ['线上直营', '电商平台', '经销商', '直播带货', '线下门店']

# 建表语句，字段与 sales_assistant.py 的 system prompt 保持一致
CREATE_TABLE_SQL = """
CREATE TABLE sales (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date TEXT    NOT NULL,   -- 订单日期 YYYY-MM-DD
    province  TEXT    NOT NULL,   -- 省份
    channel   TEXT    NOT NULL,   -- 销售渠道
    quantity  INTEGER NOT NULL,   -- 销量
    amount    REAL    NOT NULL    -- 销售金额(元)
)
"""


def generate_rows():
    """生成销售订单数据：每个「月份-省份-渠道」组合 2~3 条订单"""
    random.seed(42)  # 固定随机种子，保证数据可复现
    rows = []
    for month in MONTHS:
        year, mon = map(int, month.split('-'))
        max_day = calendar.monthrange(year, mon)[1]
        for province in PROVINCES:
            for channel in CHANNELS:
                for _ in range(random.randint(2, 3)):
                    day = random.randint(1, max_day)
                    quantity = random.randint(10, 200)
                    unit_price = round(random.uniform(50, 500), 2)
                    rows.append((
                        f'{month}-{day:02d}',
                        province,
                        channel,
                        quantity,
                        round(quantity * unit_price, 2),
                    ))
    return rows


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        # 先删除旧表，保证重复运行得到同一份数据
        conn.execute('DROP TABLE IF EXISTS sales')
        conn.execute(CREATE_TABLE_SQL)
        rows = generate_rows()
        conn.executemany(
            'INSERT INTO sales (sale_date, province, channel, quantity, amount) VALUES (?, ?, ?, ?, ?)',
            rows,
        )
        conn.commit()
        print(f'已生成 {len(rows)} 行销售数据，数据库文件：{DB_PATH}')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
