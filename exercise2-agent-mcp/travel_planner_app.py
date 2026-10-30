"""行程图生成界面：用自然语言提问，得到可打印的 A4 行程页面

一次提问内部拆成两步，且用两个不同的助手：
1. 规划助手（case-mcp 的高德地图助手，带 MCP 工具）：查真实路线与驾车里程，输出行程要点
2. 排版助手（不带工具、关闭思考）：把行程按 A4 模板渲染成完整 HTML

这样拆是因为：
- 一次性「边查地图边输出上千行 HTML」会被服务端断开长连接
- 带着地图工具去生成 HTML，模型会把输出当成工具调用，导致解析失败

生成的 HTML 保存为 travel_planner.html 并在浏览器打开，用户 Cmd+P 即可打印成图。

运行方式：
    set -a; source .env; set +a      # 加载 DASHSCOPE_API_KEY 与 AMAP_MAPS_API_KEY
    .venv/bin/python exercise2-agent-mcp/travel_planner_app.py
"""

import os
import re
import sys
import webbrowser

import gradio as gr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 复用 case-mcp 里已调通的高德地图助手
CASE_MCP_DIR = os.path.join(BASE_DIR, '..', 'case-mcp')
# A4 行程表模板与生成的行程页面
TEMPLATE_PATH = os.path.join(CASE_MCP_DIR, '旅行规划.md')
OUTPUT_PATH = os.path.join(BASE_DIR, 'travel_planner.html')
# 排版用的模型
MODEL = 'qwen3.8-max'

sys.path.insert(0, CASE_MCP_DIR)
import assistant_mcp_amap_bot as amap_bot  # noqa: E402  需要先插入模块搜索路径
import generate_travel_planner as planner  # noqa: E402  复用其中的助手构造逻辑

# 复用实例，避免每轮对话都重新启动 MCP 服务
_plan_bot = None
_render_bot = None


def get_plan_bot():
    """带高德地图 MCP 的规划助手，懒加载

    用 generate_travel_planner 里的构造逻辑：模型统一、关闭思考，
    避免思考过程占满输出预算导致助手只回一句开场白就停住。
    """
    global _plan_bot
    if _plan_bot is None:
        _plan_bot = planner.init_agent_service(MODEL, with_tools=True)
    return _plan_bot


def get_render_bot():
    """不带工具、关闭思考的排版助手，懒加载"""
    global _render_bot
    if _render_bot is None:
        _render_bot = planner.init_agent_service(MODEL, with_tools=False)
    return _render_bot


def run_once(bot, prompt):
    """跑一轮对话，返回助手输出的正文"""
    last = None
    for rsp in bot.run([{'role': 'user', 'content': prompt}]):
        last = rsp
    parts = [m['content'] for m in last
             if m.get('role') == 'assistant' and isinstance(m.get('content'), str) and m['content'].strip()]
    return '\n\n'.join(parts).strip()


def extract_html(text):
    """从回复中提取完整 HTML：优先取 ```html 代码块，其次截取 <html 到 </html>"""
    blocks = re.findall(r'```html\s*(.*?)```', text, re.S)
    if blocks:
        return max(blocks, key=len).strip()
    start = text.find('<!DOCTYPE html')
    if start == -1:
        start = text.find('<html')
    end = text.rfind('</html>')
    if start == -1 or end == -1:
        return ''
    return text[start:end + len('</html>')].strip()


def respond(message, history):
    """处理一轮提问：先查路线出行程要点，再渲染成 A4 HTML 并打开"""
    # 第一步：只要行程要点，避免模型被地图返回的逐步导航数据淹没
    # 限制工具调用次数：调用越多越容易出现无法解析的调用参数，导致这一轮提前中断
    plan_prompt = (f'{message}\n'
                   '请最多调用 3 次地图工具查询主要路段的驾车里程，然后按天输出：'
                   '第几天、出发地与目的地、主要景点、驾车里程、住宿与餐饮建议。'
                   '用 Markdown 列表输出，不要罗列逐步导航细节，也不要输出 HTML。')
    trip_text = run_once(get_plan_bot(), plan_prompt)
    if len(trip_text) < 100:
        return f'地图助手没有返回完整行程，请换个说法再试一次。\n\n助手原文：{trip_text}'

    # 第二步：用不带工具的排版助手渲染完整 HTML
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        template = f.read()
    render_prompt = (f'下面是模板要求：\n{template}\n\n'
                     f'下面是行程内容：\n{trip_text}\n\n'
                     '请把上面的行程按模板要求渲染成一份完整、可直接打印的 A4 行程表 HTML。\n'
                     '只输出一个 ```html 代码块，不要省略任何内容区块，也不要输出解释文字。')
    reply = run_once(get_render_bot(), render_prompt)

    html = extract_html(reply)
    if not html:
        return f'{trip_text}\n\n（本次没有生成 HTML，请再试一次要求生成 A4 行程表）'

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    webbrowser.open('file://' + OUTPUT_PATH)
    # 回复里不贴整段 HTML，避免刷屏
    brief = re.sub(r'```html.*?```', '（A4 行程页面已生成）', reply, flags=re.S)
    return (f'{trip_text}\n\n---\n{brief}\n\n'
            f'已保存并在浏览器打开：{OUTPUT_PATH}\n'
            '在浏览器里按 Cmd+P 即可打印成 PDF，或者截图保存成图片。')


if __name__ == '__main__':
    gr.ChatInterface(
        respond,
        title='行程图生成助手',
        description='用自然语言描述行程，助手会调用高德地图查真实路线与里程，再生成 A4 可打印的行程页面（内部分两步，需要一到三分钟）',
        examples=['北京三日游', '成都出发的5天自驾游', '上海到杭州的周末两日游'],
    ).launch(server_port=7861, server_name='127.0.0.1')
