"""生成 A4 可打印的自驾游行程表

分两步完成：
1. 调用高德地图 MCP 查询真实路线与驾车里程，得到按天的行程内容
2. 再按 A4 行程表模板（case-mcp/旅行规划.md）把行程渲染成完整可打印的 HTML

拆成两步是为了稳定：一次性让模型边查地图边输出上千行 HTML，容易被服务端断开连接。

运行方式：
    set -a; source .env; set +a      # 加载 DASHSCOPE_API_KEY 与 AMAP_MAPS_API_KEY
    .venv/bin/python exercise2-agent-mcp/generate_travel_planner.py --origin 成都 --days 7

免费额度有到期时间，模型额度用尽时用 --model 换成仍有额度的模型，例如：
    .venv/bin/python exercise2-agent-mcp/generate_travel_planner.py --model qwen3.8-flash
"""

import argparse
import os
import re

from qwen_agent.agents import Assistant

# 脚本所在目录：输出文件与模板路径都基于它解析，不依赖运行目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# A4 行程表提示词模板
TEMPLATE_PATH = os.path.join(BASE_DIR, '..', 'case-mcp', '旅行规划.md')
# 生成的行程表与第一步的行程内容
OUTPUT_PATH = os.path.join(BASE_DIR, 'travel_planner.html')
TRIP_PATH = os.path.join(BASE_DIR, 'trip_plan.md')


def init_agent_service(model, with_tools):
    """初始化助手：模型走百炼 OpenAI 兼容通道

    with_tools 为 True 时挂高德地图 MCP（规划行程用）；
    为 False 时不挂工具、并关闭思考（渲染长 HTML 用，避免生成过慢被服务端断开）
    """
    # 两个助手都关闭思考：思考过程会占满输出预算，导致只回一句开场白就没有正文
    generate_cfg = {
        'max_input_tokens': 58000,
        # A4 行程表的完整 HTML 通常上万 token，输出上限给足
        'max_tokens': 16000,
        # enable_thinking 要放进 extra_body 才会进入请求体
        'extra_body': {'enable_thinking': False},
    }
    llm_cfg = {
        'model': model,
        # 走百炼的 OpenAI 兼容通道，原生 DashScope 通道不支持这些模型
        'model_server': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'api_key': os.getenv('DASHSCOPE_API_KEY'),
        'timeout': 300,  # 长输出，超时放宽
        'retry_count': 3,
        'generate_cfg': generate_cfg,
    }
    if with_tools:
        system = ('你扮演一个地图助手，你具有查询地图、规划路线、推荐景点等能力。'
                  '规划行程时先调用地图工具查询真实路线与驾车里程，再给出结果。')
        function_list = [{
            'mcpServers': {
                'amap-maps': {
                    'command': 'npx',
                    'args': ['-y', '@amap/amap-maps-mcp-server'],
                    'env': {'AMAP_MAPS_API_KEY': os.getenv('AMAP_MAPS_API_KEY')},
                }
            }
        }]
        name, description = '地图助手', '地图查询与路线规划'
    else:
        system = '你是平面设计师兼前端开发工程师，擅长把行程内容排版成可打印的 A4 页面。'
        function_list = []
        name, description = '行程排版助手', '把行程内容排版成可打印的 A4 页面'
    return Assistant(
        llm=llm_cfg,
        name=name,
        description=description,
        system_message=system,
        function_list=function_list,
    )


def run_once(bot, prompt):
    """跑一轮对话，返回助手输出的正文

    汇总整轮里所有助手消息，避免最后一轮停在工具调用结果上而拿不到正文。
    """
    last = None
    for rsp in bot.run([{'role': 'user', 'content': prompt}]):
        last = rsp
    parts = [m['content'] for m in last
             if m.get('role') == 'assistant' and isinstance(m.get('content'), str) and m['content'].strip()]
    return '\n\n'.join(parts).strip()


def extract_html(text):
    """从模型回复中提取完整 HTML：优先取 ```html 代码块，其次截取 <html 到 </html>"""
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


def main():
    parser = argparse.ArgumentParser(description='生成 A4 可打印的自驾游行程表')
    parser.add_argument('--origin', default='成都', help='出发地，默认成都')
    parser.add_argument('--days', type=int, default=7, help='行程天数，默认 7 天')
    parser.add_argument('--model', default='qwen3.8-max', help='模型名，默认 qwen3.8-max')
    args = parser.parse_args()

    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        template = f.read()

    # 第一步：带地图 MCP，规划出带真实里程的行程内容
    plan_bot = init_agent_service(args.model, with_tools=True)
    plan_prompt = (f'请规划一条从{args.origin}出发的{args.days}天自驾游路线。\n'
                   '先用地图工具查询每一天路段的真实驾车里程与途经城市，然后按天输出：'
                   '第几天、出发地与目的地、主要景点、驾车里程、住宿与餐饮建议。\n'
                   '用 Markdown 列表输出，不要输出 HTML。')
    print(f'第一步：规划从{args.origin}出发的{args.days}天自驾游行程...')
    trip_text = run_once(plan_bot, plan_prompt)
    if len(trip_text) < 200:
        raise RuntimeError(f'行程内容过短（{len(trip_text)} 字符），地图助手未返回完整行程，请重试')
    # 先落盘，避免第二步失败时丢失已查好的路线数据
    with open(TRIP_PATH, 'w', encoding='utf-8') as f:
        f.write(trip_text)
    print(f'行程内容已生成（{len(trip_text)} 字符），保存至：{TRIP_PATH}')

    # 第二步：不挂工具、关闭思考，把行程渲染成 A4 HTML
    render_bot = init_agent_service(args.model, with_tools=False)
    render_prompt = (f'下面是模板要求：\n{template}\n\n'
                     f'下面是从{args.origin}出发的{args.days}天自驾游行程内容：\n{trip_text}\n\n'
                     '请把上面的行程内容按模板要求，输出一份完整、可直接打印的 A4 行程表 HTML。\n'
                     '只输出一个 ```html 代码块，不要省略任何内容区块，也不要输出解释文字。')
    print('第二步：把行程渲染成 A4 HTML...')
    html = extract_html(run_once(render_bot, render_prompt))
    if not html:
        raise RuntimeError('未从模型回复中提取到 HTML，请缩短天数或换模型后重试')

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'已生成 {len(html)} 字符，保存至：{OUTPUT_PATH}')


if __name__ == '__main__':
    main()
