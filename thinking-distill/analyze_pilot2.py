#!/usr/bin/env python3
"""T1 pilot 分析之二：失败轨迹是否"找到了却没买"，失败模式分类。"""
import json, re, os
from collections import Counter

TASKS = [int(x) for x in open('/root/autodl-tmp/thinking-distill/t1_pilot/pilot_task_ids.txt').read().split()]
GOALS = json.load(open('/root/autodl-tmp/runs/asin_audit/goals_reconstructed.json'))
COND_PATHS = {
    'base':   '/root/autodl-tmp/runs/shop_sft_512/raw/{:06d}/000.json',
    'medium': '/root/autodl-tmp/thinking-distill/t1_pilot/full/raw/{:06d}/000.json',
    'low':    '/root/autodl-tmp/thinking-distill/t1_pilot/low/raw/{:06d}/000.json',
}

SAT = re.compile(r'满足|符合(所有|全部|要求)|matches? (all|the)|satisf|✓|perfect fit|exactly what|就是它|符合要求|符合指令|fits? the|in budget|within (the )?budget|预算内', re.I)
HESIT = re.compile(r'确认|核实|verify|check|再看|让我.{0,6}(看|查)|let me (check|verify|look)|不确定|无法|not (sure|shown|mentioned|listed|clear)|doesn\'t (show|say|mention)|缺少|没有(显示|标明|提到)', re.I)

def load(cond, task):
    p = COND_PATHS[cond].format(task)
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    seq = []  # (thinking_text, action)
    for m in d['messages']:
        if m.get('role') != 'assistant':
            continue
        think, act = '', None
        for c in m.get('content', []):
            if c.get('type') == 'thinking':
                think += c.get('thinking', '')
            elif c.get('type') == 'toolCall' and c.get('name') == 'shop_act':
                act = c.get('arguments', {}).get('action', '?')
        if act:
            seq.append((think, act))
    return {'accepted': d['accepted'], 'done': d['done'], 'reward': d['reward'],
            'turns': d['tool_calls'], 'seq': seq}

def clicks_asins(seq):
    return [a[6:-1] for _, a in seq if a.startswith('click[') and re.fullmatch(r'\d{6,}', a[6:-1])]

print('表5 medium 失败轨迹：goal 商品是否出现过、出现后教师干什么了')
print(f'{"task":>6} | {"goal访问":>4} {"首访turn":>4} {"访后动作":>4} | {"宣告满足却没买":>6} | goal options')
print('-' * 110)
for t in TASKS:
    r = load('medium', t)
    if not r or r['accepted']:
        continue
    g = GOALS[t]
    gasin = g['asin']
    asins = clicks_asins(r['seq'])
    visited = gasin in asins
    first_turn = next((i for i, (_, a) in enumerate(r['seq']) if a == f'click[{gasin}]'), None)
    after = len(r['seq']) - first_turn - 1 if first_turn is not None else None
    # 宣告满足但下一步不是 buy
    sat_nobuy = 0
    for i, (th, a) in enumerate(r['seq'][:-1]):
        if SAT.search(th) and 'buy' not in r['seq'][i + 1][1].lower():
            sat_nobuy += 1
    opts = ','.join(g.get('goal_options', []))[:40]
    fa = f'{first_turn:>4}' if first_turn is not None else f'{"--":>4}'
    af = f'{after:>4}' if after is not None else f'{"--":>4}'
    print(f'{t:>6} | {"Y" if visited else "N":>6} {fa} {af} | {sat_nobuy:>10} | {opts}')

print()
print('表6 "满足宣告→不买"与"犹豫词"在 medium 成功 vs 失败中的密度')
for label, pred in [('medium失败', lambda r: not r['accepted']), ('medium成功', lambda r: r['accepted'])]:
    sat_nb, hes, total = 0, 0, 0
    for t in TASKS:
        r = load('medium', t)
        if not r or not pred(r):
            continue
        for i, (th, a) in enumerate(r['seq']):
            if not th.strip():
                continue
            total += 1
            if HESIT.search(th):
                hes += 1
            if i + 1 < len(r['seq']) and SAT.search(th) and 'buy' not in r['seq'][i + 1][1].lower():
                sat_nb += 1
    print(f'{label}: 犹豫词turn {hes}/{total} ({hes/max(total,1)*100:.0f}%), 宣告满足却没买 {sat_nb} 次')

print()
print('表7 low 条件失败轨迹同样的检查')
print(f'{"task":>6} | {"goal访问":>4} {"首访turn":>4} {"访后动作":>4} | {"宣告满足却没买":>6}')
print('-' * 70)
for t in TASKS:
    r = load('low', t)
    b = load('base', t)
    if not r or r['accepted'] or not (b and b['accepted']):
        continue
    g = GOALS[t]
    asins = clicks_asins(r['seq'])
    visited = g['asin'] in asins
    first_turn = next((i for i, (_, a) in enumerate(r['seq']) if a == f"click[{g['asin']}]"), None)
    after = len(r['seq']) - first_turn - 1 if first_turn is not None else None
    sat_nobuy = sum(1 for i, (th, a) in enumerate(r['seq'][:-1])
                    if SAT.search(th) and 'buy' not in r['seq'][i + 1][1].lower())
    fa = f'{first_turn:>4}' if first_turn is not None else f'{"--":>4}'
    af = f'{after:>4}' if after is not None else f'{"--":>4}'
    print(f'{t:>6} | {"Y" if visited else "N":>6} {fa} {af} | {sat_nobuy:>10}')

print()
print('表8 前半程 vs 后半程动作重复率（medium 失败，验证"先正常后打转"）')
for t in TASKS:
    r = load('medium', t)
    if not r or r['accepted']:
        continue
    acts = [a for _, a in r['seq']]
    h1, h2 = acts[:10], acts[-15:]
    rep = lambda xs: 1 - len(set(xs)) / max(len(xs), 1)
    print(f'{t:>6}: 前10动 重复率{rep(h1):.2f} | 后15动 重复率{rep(h2):.2f} | 动作总数{len(acts)}')
