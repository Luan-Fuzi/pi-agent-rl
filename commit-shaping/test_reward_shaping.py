"""Unit tests for reward_shaping.py (no slime/torch needed).

Loads the module fresh per variant via importlib, with synthetic tables in a
temp dir. Covers the legacy audit-driven variants (regression, from
runs/reward_shaping/test_reward_shaping.py) plus the commit-shaping
process-level components (milestones / antiloop / efficiency).

Run: python3 commit-shaping/test_reward_shaping.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

MODULE = str(Path(__file__).resolve().parents[1] / "slime/examples/ShopSimulator/reward_shaping.py")

# synthetic world: task 1 has n_attr=2, n_opt=1, budget=100; task 2 has no budget
DIMS = {"1": {"n_attr": 2, "n_opt": 1, "goal_asin": "G"}, "2": {"n_attr": 2, "n_opt": 1, "goal_asin": "G2"}}
BUDGETS = {"1": {"budget": 100.0, "method": "yuan"}}
PRICES = {"P_OK": 100.0, "P_OVER": 120.0, "P_EDGE": 110.0}

ENV_KEYS = (
    "SHOP_REWARD_SHAPING", "SHOP_REWARD_OPTION_WEIGHT", "SHOP_REWARD_BUDGET_TOL",
    "SHOP_REWARD_TABLE_DIR", "SHOP_REWARD_MILESTONES", "SHOP_REWARD_REOPEN_PENALTY",
    "SHOP_REWARD_REPEAT_SEARCH_PENALTY", "SHOP_REWARD_LOOP_BACK_PENALTY",
    "SHOP_REWARD_REOPEN_FREE", "SHOP_REWARD_EFFICIENCY_EPS",
    "SHOP_REWARD_EFFICIENCY_FREE_TURNS", "SHOP_REWARD_EFFICIENCY_SPAN",
)


def load_module(variant=None, table_dir=None, **knobs):
    env = {"SHOP_REWARD_SHAPING": variant or "", "SHOP_REWARD_TABLE_DIR": table_dir or ""}
    env.update({k: str(v) for k, v in knobs.items()})
    old = {k: os.environ.get(k) for k in ENV_KEYS}
    try:
        for k in ENV_KEYS:
            v = env.get(k, "")
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        spec = importlib.util.spec_from_file_location("reward_shaping_ut", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def detail(attr=2.0, opt=0.0, r_price=1.0, r_type=1.0):
    return {"num_attr_matches": attr, "num_option_matches": opt, "r_price": r_price, "r_type": r_type}


def approx(a, b, eps=1e-9):
    return abs(a - b) <= eps


def main():
    tmp = tempfile.mkdtemp()
    json.dump(DIMS, open(f"{tmp}/task_dims.json", "w"))
    json.dump(BUDGETS, open(f"{tmp}/task_budget.json", "w"))
    json.dump(PRICES, open(f"{tmp}/prices.json", "w"))

    n_pass = n_fail = 0

    def check(name, cond):
        nonlocal n_pass, n_fail
        n_pass, n_fail = n_pass + cond, n_fail + (not cond)
        print(f"  {'PASS' if cond else 'FAIL <<<'}  {name}")

    # ---- legacy regression (off / option_gate / budget / full) ----
    # env formula for task1: (attr + opt + r_price) / (2+1+1) * r_type = sum/4
    # 1. off: passthrough even with full detail
    m = load_module(table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK")
    check("off: 原样透传", approx(r, 0.75) and meta == {})
    check("off: shaping_enabled=False", not m.shaping_enabled())

    # 2. option_gate, r_option=0: env .75 -> (2+2*0+1)/(2+2*1+1)=3/5=.6
    m = load_module("option_gate", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(opt=0.0), "P_OK")
    check("option_gate: r_option=0 降权", approx(r, 0.6) and meta["w_opt"] == 2.0)

    # 3. option_gate, r_option=1: env 1.0 -> (2+2*1+1)/5=1.0
    r, _ = m.shape_reward(1, 1.0, detail(opt=1.0), "P_OK")
    check("option_gate: r_option=1 满分不变", approx(r, 1.0))

    # 4. option_gate partial: env (1+1+1)/4=.75 -> (1+2*1+1)/5=.8
    r, _ = m.shape_reward(1, 0.75, detail(attr=1.0, opt=1.0), "P_OK")
    check("option_gate: 部分命中重排", approx(r, 0.8))

    # 5. budget within: price 100 <= 110 -> unchanged
    m = load_module("budget", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK")
    check("budget: 预算内不变", approx(r, 0.75) and meta["r_price_instr"] == 1.0)

    # 6. budget over: price 120 > 110 -> (2+0+0)/4 = .5
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OVER")
    check("budget: 超预算 r_price=0", approx(r, 0.5) and meta["r_price_instr"] == 0.0
          and approx(meta["price_paid"], 120.0) and approx(meta["limit"], 110.0, eps=1e-6))

    # 7. boundary: price == limit (110) -> within
    r, _ = m.shape_reward(1, 0.75, detail(), "P_EDGE")
    check("budget: 边界值(=limit)不算超", approx(r, 0.75))

    # 8. env r_price already 0 + 预算内 -> 保持 0（只收紧不放松）
    r, _ = m.shape_reward(1, 0.5, detail(r_price=0.0), "P_OK")
    check("budget: env r_price=0 不被放松", approx(r, 0.5))

    # 9. task 无预算信息 -> 不变
    r, meta = m.shape_reward(2, 0.75, detail(), "P_OVER")
    check("budget: 无预算条目跳过", approx(r, 0.75) and "r_price_instr" not in meta)

    # 10. asin 无价格 -> 不变
    r, _ = m.shape_reward(1, 0.75, detail(), "P_UNKNOWN")
    check("budget: 无价格条目跳过", approx(r, 0.75))

    # 11. full: r_option=0 且超预算 -> (2+2*0+0)/(2+2+1)=.4
    m = load_module("full", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OVER")
    check("full: 双重生效", approx(r, 0.4) and meta["w_opt"] == 2.0 and meta["r_price_instr"] == 0.0)

    # 12. detail 缺失 -> 透传
    r, meta = m.shape_reward(1, 0.0, None, "P_OK")
    check("enabled 但无 detail: 透传", approx(r, 0.0) and meta == {})

    # 13. detail 缺字段 -> 透传 + shaping_error
    r, meta = m.shape_reward(1, 0.75, {"num_attr_matches": 1.0}, "P_OK")
    check("detail 不完整: 透传并报错标记", approx(r, 0.75) and "shaping_error" in meta)

    # 14. task 不在 dims 表 -> 透传 + shaping_error
    r, meta = m.shape_reward(999, 0.75, detail(), "P_OK")
    check("未知 task_id: 透传并报错标记", approx(r, 0.75) and "shaping_error" in meta)

    # 15. 自定义 w_opt=4: (2+4*0+1)/(2+4*1+1)=3/7
    m = load_module("option_gate", SHOP_REWARD_OPTION_WEIGHT=4.0, table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK")
    check("自定义 OPTION_WEIGHT 生效", approx(r, 3.0 / 7.0) and meta["w_opt"] == 4.0)

    # 16. 自定义 tol=1.0: price 100 <= 100 -> 不变; 但 P_EDGE=110 超
    m = load_module("budget", SHOP_REWARD_BUDGET_TOL=1.0, table_dir=tmp)
    r, _ = m.shape_reward(1, 0.75, detail(), "P_EDGE")
    check("自定义 BUDGET_TOL 生效", approx(r, 0.5))

    # 17. 表目录不存在 -> 全部透传不炸
    m = load_module("full", table_dir="/nonexistent_dir_xyz")
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK")
    check("表缺失: 透传不炸", approx(r, 0.75) and "shaping_error" in meta)

    # ---- compute_process_stats ----
    m = load_module(table_dir=tmp)
    s = m.compute_process_stats([])
    check("stats: 空序列 level 0", s["milestone_level"] == 0 and s["n_actions"] == 0)

    s = m.compute_process_stats(["search[a]", "search[a]", "search[  a ]", "search[b]"])
    check("stats: 搜索词归一去重", s["search_count"] == 4 and s["unique_search_terms"] == 2
          and s["repeated_search_count"] == 2)

    s = m.compute_process_stats(["click[123]", "click[123]", "click[456]"])
    check("stats: asin 打开/重开", s["product_page_opens"] == 3 and s["unique_asins"] == 2
          and s["asin_reopens"] == 1 and s["asin_open_counts"] == {"123": 2, "456": 1}
          and s["milestone_level"] == 1)

    s = m.compute_process_stats(["click[123]", "click[红色 M码]", "click[buy now]"])
    check("stats: 规格点击 + buy → level 3", s["option_clicks"] == 1 and s["buy_attempts"] == 1
          and s["milestone_level"] == 3)

    s = m.compute_process_stats(["click[Buy Now]"])
    check("stats: buy 大小写不敏感", s["buy_attempts"] == 1 and s["milestone_level"] == 3)

    # back-to-search loop: new asin before first back → free; reopen then back → loop
    s = m.compute_process_stats([
        "click[111]", "click[back to search]",
        "click[111]", "click[back to search]",
        "click[222]", "click[back to search]",
    ])
    check("stats: 无新候选的 back 记 loop", s["back_to_search_count"] == 3 and s["loop_back_count"] == 1)

    s = m.compute_process_stats(["click[description]", "click[features]", "click[next page]", "garbage"])
    check("stats: info/翻页/ malformed 分类", s["info_clicks"] == 2 and s["pagination_clicks"] == 1
          and s["malformed_actions"] == 1 and s["milestone_level"] == 0)

    # ---- milestones ----
    m = load_module("milestones", table_dir=tmp)
    stats = m.compute_process_stats(["click[123]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("milestones: 开页 level1 → 0.05", approx(r, 0.05) and meta["milestone_level"] == 1)

    stats = m.compute_process_stats(["click[123]", "click[红色]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("milestones: 选规格 level2 → 0.10", approx(r, 0.10) and meta["milestone_level"] == 2)

    stats = m.compute_process_stats(["click[123]", "click[buy now]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("milestones: 点过 buy level3 → 0.15", approx(r, 0.15) and meta["milestone_level"] == 3)

    stats = m.compute_process_stats(["search[abc]", "search[abc]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("milestones: 只搜索 level0 → 0.0", approx(r, 0.0) and meta["milestone_level"] == 0)

    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, process_stats=stats, model_turns=30)
    check("milestones: done 轨迹分文不动", approx(r, 0.75) and meta == {})

    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=None)
    check("milestones: 无 stats 透传", approx(r, 0.0) and meta == {})

    m = load_module("milestones", SHOP_REWARD_MILESTONES="0,0.1,0.2,0.3", table_dir=tmp)
    stats = m.compute_process_stats(["click[123]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("milestones: 自定义阶梯生效", approx(r, 0.1))

    try:
        load_module("milestones", SHOP_REWARD_MILESTONES="0.2,0.1,0.3,0.4", table_dir=tmp)
        check("milestones: 非法阶梯 import 期报错", False)
    except ValueError:
        check("milestones: 非法阶梯 import 期报错", True)

    # ---- antiloop ----
    m = load_module("milestones+antiloop", table_dir=tmp)
    stats = m.compute_process_stats([
        "click[111]", "click[back to search]", "click[111]", "click[back to search]",
        "search[x]", "search[x]", "click[111]", "click[buy now]",
    ])
    # level 3 (0.15); reopens of 111 = 2 (opens 3, free 0) → .04; repeated search 1 → .02;
    # loop backs: back#2 has no new asin since back#1 → 1 → .01; total penalty .07 → .08
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("antiloop: 重开+重复搜索+loop 罚则", approx(r, 0.08) and approx(meta["antiloop_penalty"], 0.07)
          and approx(meta["penalty_reopen"], 0.04) and approx(meta["penalty_repeat_search"], 0.02)
          and approx(meta["penalty_loop_back"], 0.01))

    stats = m.compute_process_stats(["click[111]"] * 20)
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("antiloop: 罚额不下探到负", approx(r, 0.0))

    m = load_module("milestones+antiloop", SHOP_REWARD_REOPEN_FREE=1, table_dir=tmp)
    stats = m.compute_process_stats(["click[111]", "click[111]", "click[111]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("antiloop: REOPEN_FREE=1 首次重开免罚", approx(meta["penalty_reopen"], 0.02))

    m = load_module("antiloop", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("antiloop: 无 milestones 不单独生效", approx(r, 0.0) and meta == {})

    m = load_module("milestones+antiloop", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, process_stats=stats)
    check("antiloop: done 轨迹不罚", approx(r, 0.75) and meta == {})

    # ---- efficiency ----
    m = load_module("efficiency", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, model_turns=10)
    check("efficiency: ≤15 轮不折", approx(r, 0.75) and approx(meta["efficiency_factor"], 1.0))

    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, model_turns=35)
    check("efficiency: 35 轮 ×0.95", approx(r, 0.75 * 0.95) and approx(meta["efficiency_factor"], 0.95))

    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, model_turns=55)
    check("efficiency: 超帽轮数因子封底 0.9", approx(r, 0.75 * 0.9))

    r, meta = m.shape_reward(1, 0.75, detail(), "P_OK", done=True, model_turns=None)
    check("efficiency: 无 model_turns 透传", approx(r, 0.75) and meta == {})

    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats, model_turns=40)
    check("efficiency: 非 done 不生效", approx(r, 0.0) and meta == {})

    # ---- composition ----
    m = load_module("option_gate+milestones", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.75, detail(opt=0.0), "P_OK", done=True)
    check("组合: done 走 recompose", approx(r, 0.6) and meta["w_opt"] == 2.0)
    stats = m.compute_process_stats(["click[123]", "click[buy now]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("组合: 非 done 走 milestone", approx(r, 0.15))

    m = load_module("milestones+antiloop+efficiency", table_dir=tmp)
    r, meta = m.shape_reward(1, 0.8, detail(opt=1.0), "P_OK", done=True, model_turns=35)
    check("组合 E3: done 只折 efficiency（无 recompose）", approx(r, 0.8 * 0.95)
          and "w_opt" not in meta)
    stats = m.compute_process_stats(["click[111]", "click[back to search]", "click[111]"])
    r, meta = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats, model_turns=40)
    check("组合 E3: 非 done milestone - penalty", approx(r, 0.05 - 0.02)
          and "efficiency_factor" not in meta)

    # ---- variant parsing ----
    try:
        load_module("milestones+bogus", table_dir=tmp)
        check("未知组件 import 期报错", False)
    except ValueError:
        check("未知组件 import 期报错", True)

    m = load_module("Milestones+AntiLoop", table_dir=tmp)
    stats = m.compute_process_stats(["click[111]", "click[111]"])
    r, _ = m.shape_reward(1, 0.0, None, None, done=False, process_stats=stats)
    check("变体大小写/空白容错", approx(r, 0.03))

    print(f"\n{n_pass} passed, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
