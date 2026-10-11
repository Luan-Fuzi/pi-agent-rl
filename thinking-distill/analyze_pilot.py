#!/usr/bin/env python3
"""T1 pilot 数据分析：thinking 开启为什么失败率上升。"""
import json, re, os
from collections import Counter, defaultdict

TASKS = [int(x) for x in open('/root/autodl-tmp/thinking-distill/t1_pilot/pilot_task_ids.txt').read().split()]
COND_PATHS = {
    'base':   '/root/autodl-tmp/runs/shop_sft_512/raw/{:06d}/000.json',
    'medium': '/root/autodl-tmp/thinking-distill/t1_pilot/full/raw/{:06d}/000.json',
    'low':    '/root/autodl-tmp/thinking-distill/t1_pilot/low/raw/{:06d}/000.json',
}

def load(cond, task):
    p = COND_PATHS[cond].format(task)
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    actions, thinks, out_toks, reason_toks = [], [], 0, 0
    for m in d['messages']:
        if m.get('role') != 'assistant':
            continue
        u = m.get('usage') or {}
        out_toks += u.get('output', 0) or 0
        det = u.get('cost') and u.get('output')  # placeholder, usage schema varies
        for c in m.get('content', []):
            if c.get('type') == 'thinking':
                thinks.append(c.get('thinking', ''))
            elif c.get('type') == 'toolCall' and c.get('name') == 'shop_act':
                actions.append(c.get('arguments', {}).get('action', '?'))
    return {
        'task': task, 'accepted': d['accepted'], 'done': d['done'],
        'reward': d['reward'], 'turns': d['tool_calls'],
        'actions': actions, 'thinks': thinks,
        'error': d.get('error') or '',
    }

def loop_stats(actions):
    """打转量化：重复动作、重访商品、验证类点击。"""
    clicks = [a[6:-1] for a in actions if a.startswith('click[')]
    searches = [a[7:-1] for a in actions if a.startswith('search[')]
    asins = [c for c in clicks if re.fullmatch(r'\d{6,}', c)]
    n = len(actions)
    if n == 0:
        return {}
    cnt = Counter(actions)
    repeated_action = sum(v - 1 for v in cnt.values())          # 完全相同的动作重复次数
    asin_cnt = Counter(asins)
    revisits = sum(v - 1 for v in asin_cnt.values())            # 同一商品重复点击
    verify_clicks = sum(1 for c in clicks if any(
        k in c.lower() for k in ['feature', 'description', 'spec', 'review']))
    buy = sum(1 for c in clicks if 'buy' in c.lower())
    return {
        'n_act': n, 'n_search': len(searches), 'n_click': len(clicks),
        'repeat_act': repeated_action, 'repeat_act_rate': repeated_action / n,
        'uniq_asin': len(asin_cnt), 'revisit': revisits,
        'verify_click': verify_clicks, 'buy_click': buy,
        'max_asin_visits': max(asin_cnt.values()) if asin_cnt else 0,
    }

UNCERTAIN = re.compile(r'确认|再检查|再核|verify|check again|let me re|无法|不确定|doesn\'t (show|mention)|not (shown|mentioned|listed)|无法证实|还是|但页面|没有(显示|提到|找到)', re.I)

data = defaultdict(dict)
for cond in COND_PATHS:
    for t in TASKS:
        r = load(cond, t)
        if r:
            data[t][cond] = r

print('=' * 100)
print('表1 逐任务结局矩阵（A=accepted, 数字=turns, R=reward）')
print(f'{"task":>6} | {"base":>14} | {"medium":>14} | {"low":>14} | 备注')
print('-' * 100)
for t in TASKS:
    row = data[t]
    cells, note = [], ''
    for cond in ['base', 'medium', 'low']:
        r = row.get(cond)
        if not r:
            cells.append(f'{"--":>14}')
            continue
        mark = 'A' if r['accepted'] else ('D' if r['done'] else 'X')
        cells.append(f'{mark} t={r["turns"]:>2} r={r["reward"]:.2f}')
    b, m = row.get('base'), row.get('medium')
    if b and m:
        if b['accepted'] and not m['accepted']:
            note = '退化'
        elif not b['accepted'] and m['accepted']:
            note = '改善'
    print(f'{t:>6} | {cells[0]:>14} | {cells[1]:>14} | {cells[2]:>14} | {note}')

print()
print('=' * 100)
print('表2 打转行为量化（medium 失败 vs base 成功，同任务对比）')
print(f'{"task":>6} | {"cond":>6} | {"act":>3} {"srch":>4} {"clk":>3} | {"重复动作":>4} {"重访ASIN":>4} {"验证点击":>4} {"buy":>3} {"单品最访":>4} | 思考总字符')
print('-' * 100)
for t in TASKS:
    row = data[t]
    b, m = row.get('base'), row.get('medium')
    if not (b and m and b['accepted'] and not m['accepted']):
        continue
    for cond, r in [('base', b), ('medium', m)]:
        s = loop_stats(r['actions'])
        if not s:
            continue
        tt = sum(len(x) for x in r['thinks'])
        print(f'{t:>6} | {cond:>6} | {s["n_act"]:>3} {s["n_search"]:>4} {s["n_click"]:>3} | '
              f'{s["repeat_act"]:>8} {s["revisit"]:>8} {s["verify_click"]:>8} {s["buy_click"]:>3} {s["max_asin_visits"]:>6} | {tt}')

print()
print('=' * 100)
print('表3 汇总：medium 成功(12) vs medium 失败(12) vs base 成功轨迹')
def agg(rs):
    ks = ['n_act', 'n_search', 'repeat_act', 'revisit', 'verify_click', 'buy_click', 'uniq_asin']
    out = {k: [] for k in ks}
    think_chars, uncertain_turns, total_think_turns = [], 0, 0
    for r in rs:
        s = loop_stats(r['actions'])
        if not s:
            continue
        for k in ks:
            out[k].append(s[k])
        tc = [len(x) for x in r['thinks']]
        think_chars.append(sum(tc))
        uncertain_turns += sum(1 for x in r['thinks'] if UNCERTAIN.search(x))
        total_think_turns += len(r['thinks'])
    n = len(out['n_act'])
    avg = {k: sum(v) / max(len(v), 1) for k, v in out.items()}
    return n, avg, sum(think_chars) / max(n, 1), uncertain_turns, total_think_turns

groups = {
    'medium失败(打转)': [data[t]['medium'] for t in TASKS if 'medium' in data[t] and not data[t]['medium']['accepted']],
    'medium成功':      [data[t]['medium'] for t in TASKS if 'medium' in data[t] and data[t]['medium']['accepted']],
    'base成功(同24任务)': [data[t]['base'] for t in TASKS if 'base' in data[t] and data[t]['base']['accepted']],
}
for name, rs in groups.items():
    n, avg, think_avg, unc, tt = agg(rs)
    print(f'{name:>18}: n={n:>2} | 平均动作 {avg["n_act"]:.1f} | 搜索 {avg["n_search"]:.1f} | '
          f'重复动作 {avg["repeat_act"]:.1f} | 重访ASIN {avg["revisit"]:.1f} | 验证点击 {avg["verify_click"]:.1f} | '
          f'buy {avg["buy_click"]:.1f} | 触达商品 {avg["uniq_asin"]:.1f} | 思考字符/轨迹 {think_avg:.0f} | '
          f'犹豫思考turn占比 {unc}/{tt}')

print()
print('=' * 100)
print('表4 medium 失败轨迹的"临终"思考（最后第2条思考，看卡在哪）')
for t in TASKS:
    r = data[t].get('medium')
    if not r or r['accepted'] or not r['thinks']:
        continue
    th = [x for x in r['thinks'] if x.strip()]
    tail = th[-2] if len(th) >= 2 else th[-1]
    tail = re.sub(r'\s+', ' ', tail)[:260]
    print(f'--- {t} ({r["error"][:30]}): {tail}')
