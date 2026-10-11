#!/usr/bin/env python3
"""T1 pilot 四方对比：base_old(8/31) vs base_new(9/2重跑) vs medium vs low。"""
import json, re, os
from collections import Counter

TASKS = [int(x) for x in open('/root/autodl-tmp/thinking-distill/t1_pilot/pilot_task_ids.txt').read().split()]
GOALS = json.load(open('/root/autodl-tmp/runs/asin_audit/goals_reconstructed.json'))
COND = {
    'base_old': '/root/autodl-tmp/runs/shop_sft_512/raw/{:06d}/000.json',
    'base_new': '/root/autodl-tmp/thinking-distill/t1_pilot/base/raw/{:06d}/000.json',
    'disabled': '/root/autodl-tmp/thinking-distill/t1_pilot/disabled/raw/{:06d}/000.json',
    'low':      '/root/autodl-tmp/thinking-distill/t1_pilot/low/raw/{:06d}/000.json',
    'medium':   '/root/autodl-tmp/thinking-distill/t1_pilot/full/raw/{:06d}/000.json',
    'high':     '/root/autodl-tmp/thinking-distill/t1_pilot/max/raw/{:06d}/000.json',
    'max':      '/root/autodl-tmp/thinking-distill/t1_pilot/max2/raw/{:06d}/000.json',
}
ORDER = ['base_old', 'base_new', 'disabled', 'low', 'medium', 'high', 'max']

def load(cond, task):
    p = COND[cond].format(task)
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    actions, reason_tok, out_tok = [], 0, 0
    for m in d['messages']:
        if m.get('role') != 'assistant':
            continue
        u = m.get('usage') or {}
        reason_tok += u.get('reasoning', 0) or 0
        out_tok += u.get('output', 0) or 0
        for c in m.get('content', []):
            if c.get('type') == 'toolCall' and c.get('name') == 'shop_act':
                actions.append(c.get('arguments', {}).get('action', '?'))
    clicks = [a[6:-1] for a in actions if a.startswith('click[')]
    asins = [c for c in clicks if re.fullmatch(r'\d{6,}', c)]
    return {'acc': d['accepted'], 'done': d['done'], 'r': d['reward'],
            'turns': d['tool_calls'], 'actions': actions,
            'goal_visited': GOALS[task]['asin'] in asins,
            'reason_tok': reason_tok, 'out_tok': out_tok,
            'err': (d.get('error') or '')[:30]}

data = {t: {c: load(c, t) for c in COND} for t in TASKS}

print('表1 五方结局矩阵（A=accepted X=fail，t=turns，r=reward，G=访问过goal商品）')
print(f'{"task":>6} | ' + ' | '.join(f'{c:>17}' for c in ORDER))
print('-' * (10 + 20 * len(ORDER)))
for t in TASKS:
    cells = []
    for c in ORDER:
        r = data[t][c]
        if not r:
            cells.append(f'{"--":>17}')
            continue
        mark = 'A' if r['acc'] else 'X'
        g = 'G' if r['goal_visited'] else ' '
        cells.append(f'{mark}{g} t={r["turns"]:>2} r={r["r"]:.2f}')
    print(f'{t:>6} | ' + ' | '.join(cells))

print()
print('表2 汇总')
for c in COND:
    rs = [data[t][c] for t in TASKS if data[t][c]]
    if not rs:
        print(f'{c:>9}: 无数据')
        continue
    acc = sum(r['acc'] for r in rs)
    loop_fail = sum(1 for r in rs if not r['acc'] and r['turns'] >= 40)
    print(f'{c:>9}: accepted {acc}/{len(rs)} ({acc/len(rs)*100:.0f}%) | 40轮打转失败 {loop_fail} | '
          f'平均turns {sum(r["turns"] for r in rs)/len(rs):.1f} | '
          f'总reasoning_tok {sum(r["reason_tok"] for r in rs)/1000:.0f}k | 总output {sum(r["out_tok"] for r in rs)/1000:.0f}k')

print()
print('表3 配对比较（McNemar 不和谐对）')
def mcnemar(a, b):
    only_a = sum(1 for t in TASKS if data[t][a] and data[t][b] and data[t][a]['acc'] and not data[t][b]['acc'])
    only_b = sum(1 for t in TASKS if data[t][a] and data[t][b] and not data[t][a]['acc'] and data[t][b]['acc'])
    chi2 = (only_a - only_b) ** 2 / (only_a + only_b) if (only_a + only_b) else 0
    print(f'{a:>9} vs {b:<9}: 仅{a}过={only_a} 仅{b}过={only_b} chi2={chi2:.2f}')
for a, b in [('base_new', 'disabled'), ('base_new', 'low'), ('base_new', 'medium'),
             ('disabled', 'medium'), ('medium', 'high'), ('medium', 'max'), ('high', 'max'),
             ('base_new', 'max'), ('base_new', 'base_old')]:
    mcnemar(a, b)

print()
print('表4 base_new 失败轨迹的死因')
for t in TASKS:
    r = data[t]['base_new']
    if r and not r['acc']:
        cnt = Counter(r['actions'])
        rep = sum(v - 1 for v in cnt.values())
        print(f'{t:>6}: turns={r["turns"]} r={r["r"]:.2f} goal_visited={r["goal_visited"]} 重复动作={rep} err={r["err"]}')
