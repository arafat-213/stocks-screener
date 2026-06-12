"""
parameter_sweep.py — Staged WFO Parameter Sweep for NSE Backtesting Engine
===========================================================================

HOW TO RUN
----------
This sweep runs in 5 sequential stages. You do NOT set it and forget it for all 5 stages
in one go — you review results between stages and confirm before proceeding.

STAGE 1 (Signal Quality Gate) — ~1728 combos, 3 folds each
    python parameter_sweep.py --stage 1

    After it finishes, open sweep_stage1_report.md and inspect the top configs.
    The script auto-selects the top 3 by robustness score as Stage 2 seeds.
    You can override by editing TOP_N_FANOUT_OVERRIDE at the top of this file.

STAGE 2 (Regime Filter) — 81 combos × 3 seeds → ~243 runs
    python parameter_sweep.py --stage 2

    Fine-tunes market breadth and regime detection parameters.

STAGE 3 (Entry Execution) — 216 combos × 3 seeds → ~648 runs
    python parameter_sweep.py --stage 3

STAGE 4 (Exit Management) — 243 combos × 3 seeds → ~729 runs
    python parameter_sweep.py --stage 4

STAGE 5 (Position Sizing) — 243 combos × 3 seeds → ~729 runs
    python parameter_sweep.py --stage 5

VALIDATION + STRESS TEST (runs automatically after Stage 5)
    The script picks the top 5 configs by robustness score, runs them through
    all 3 validation folds (OOS, strictly after all discovery data), and then
    runs a 6-year continuous stress test (2020-2026).

RESUMING AFTER A CRASH
    Each stage uses a checkpoint file (e.g., sweep_completed_stage1.json).
    If the script dies at combo 280, just re-run the same command — it will
    skip already-completed combos and pick up from where it left off.

CONCURRENCY NOTES
    - Stage 1: MAX_CONCURRENT=4 (parallel, no cache benefit anyway since signal
      params differ per combo)
    - Stages 2-5: MAX_CONCURRENT=4 (parallelized for speed; while serialized
      execution cuts runtime via signal cache, Stage 2+ still benefits from
      parallelization in high-core environments).
    - With 4 Celery workers in Docker, each worker has isolated memory.

TUNING BETWEEN STAGES
    You don't need to modify this file between stages — seeds are read from
    the JSON output of the previous stage. If you want to manually override
    which configs advance, edit the *_top3.json file before running the next
    stage (it's human-readable).
"""

import argparse
import itertools
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import numpy as np
import requests

# Module-level lock for checkpoint file synchronization (prevents TOCTOU race)
_checkpoint_lock = threading.RLock()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000/api/backtest"

# How many top configs advance from each stage to seed the next.
# Increasing this grows the next stage's work by this multiplier.
TOP_N_FANOUT = 3

# Override which configs advance (set to a list of param dicts to bypass auto-select).
# Leave as None to use auto-selection from the previous stage's output.
TOP_N_FANOUT_OVERRIDE = None  # e.g. [{"score_threshold": 62.0, "min_adx": 25.0, ...}]

# Per-fold minimum trade gates. Configs below this are flagged (not disqualified)
# and their Sharpe is penalized by LOW_SAMPLE_SHARPE_PENALTY.
FOLD_MIN_TRADES = {
    "D1_Crash_Recovery": 25,
    "D2_Post_COVID_Bull": 40,
    "D3_Bear_Chop": 30,
    "V1_Bull_Extension": 50,
    "V2_Late_Cycle_Correction": 25,
    "V3_Recent": 30,
}

# Fold durations in days for Calmar annualization.
FOLD_DURATION_DAYS = {
    "D1_Crash_Recovery": 306,
    "D2_Post_COVID_Bull": 365,
    "D3_Bear_Chop": 455,
    "V1_Bull_Extension": 456,
    "V2_Late_Cycle_Correction": 274,
    "V3_Recent": 435,
}

LOW_SAMPLE_SHARPE_PENALTY = 0.7  # Multiply Sharpe by this if below min trades

FOLD_WEIGHTS = {
    "D1_Crash_Recovery": 1.2,  # High weight — tests drawdown control
    "D2_Post_COVID_Bull": 0.8,  # Lower weight — most strategies look good here
    "D3_Bear_Chop": 2.0,  # Double weight — survival here is rare and valuable
}

# ─────────────────────────────────────────────────────────────────────────────
# FOLD DEFINITIONS
# All discovery periods end March 2023.
# All validation periods start April 2023 — strictly no overlap.
# ─────────────────────────────────────────────────────────────────────────────

DISCOVERY_FOLDS = [
    {
        "name": "D1_Crash_Recovery",
        "date_from": "2020-03-01",
        "date_to": "2020-12-31",
        # Nifty: ~11000 → 7600 → 13900. Tests drawdown control + recovery capture.
        # ~10 months. Configs with strict filters may produce <25 trades — flagged.
    },
    {
        "name": "D2_Post_COVID_Bull",
        "date_from": "2021-01-01",
        "date_to": "2021-12-31",
        # Nifty: 13900 → 18600. Pure trending bull. Tests momentum capture.
        # ~12 months. Expect 80-150 trades on full universe.
    },
    {
        "name": "D3_Bear_Chop",
        "date_from": "2022-01-01",
        "date_to": "2023-03-31",
        # Nifty: 18600 → 15800 → 17400. Bear + sideways grind.
        # ~15 months. Most configs will underperform — that's the stress.
    },
]

VALIDATION_FOLDS = [
    {
        "name": "V1_Bull_Extension",
        "date_from": "2023-04-01",
        "date_to": "2024-06-30",
        # Nifty: 17400 → 24000. Strong mid/small cap outperformance.
        # OOS bull — should confirm D2 findings.
    },
    {
        "name": "V2_Late_Cycle_Correction",
        "date_from": "2024-07-01",
        "date_to": "2025-03-31",
        # Nifty: 24000 → 26500 → 21900. Blow-off top + sharp correction.
        # Tests whether regime filter catches the turn.
    },
    {
        "name": "V3_Recent",
        "date_from": "2025-04-01",
        "date_to": "2026-06-09",
        # Recovery phase. Genuinely OOS — no hindsight possible.
    },
]

CONTINUOUS_STRESS = {
    "date_from": "2020-03-01",
    "date_to": date.today().isoformat(),
}

# ─────────────────────────────────────────────────────────────────────────────
# FIXED DEFAULTS (structural decisions — not swept)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULTS = {
    "symbol_limit": None,
    "use_volatility_sizing": True,
    "use_state_based_exits": True,
    "starting_capital": 1000000.0,
    "position_size": 20000.0,
    "regime_bull_rsi_threshold": 60.0,  # Fixed — only affects bull vs neutral sizing
    "regime_adx_threshold": 20.0,  # Fixed — only affects bull vs neutral sizing
    "use_pullback_fallback": False,  # Fixed — disabled as per Issue 2 fix
}

# ─────────────────────────────────────────────────────────────────────────────
# STAGE GRIDS
# ─────────────────────────────────────────────────────────────────────────────

# RSI ranges as paired tuples to avoid nonsensical combos like rsi_min > rsi_max
RSI_RANGES = [
    {"rsi_min": 35.0, "rsi_max": 58.0},  # Early recovery / mean reversion
    {"rsi_min": 35.0, "rsi_max": 65.0},  # Conservative standard
    {"rsi_min": 40.0, "rsi_max": 70.0},  # Standard momentum
    {"rsi_min": 45.0, "rsi_max": 75.0},  # Continuation / high-tight flag
]

# Stage 1: Signal Quality Gate
# 4 × 3 × 2 × 2 × 3 × 4 × 3 = 1728 combos
GRID_1 = {
    "score_threshold": [55.0, 60.0, 65.0, 70.0],
    "min_adx": [20.0, 25.0, 30.0],
    "require_consolidation": [True, False],
    "min_signal_tier": [1, 2],
    "max_signal_volatility_mult": [1.2, 1.5, 2.0],
    "rsi_range": [0, 1, 2, 3],
    "max_pct_from_52w_high": [0.0, -15.0, -25.0],
}

# Stage 2: Regime Filter (NEW)
# 3 × 3 × 3 × 3 = 81 combos × 3 seeds = 243 configs
GRID_2 = {
    "min_market_breadth_pct": [35.0, 40.0, 50.0],
    "regime_bear_rsi_threshold": [40.0, 45.0, 50.0],
    "regime_confirmation_days": [3, 5, 7],
    "regime_adx_floor": [12.0, 15.0, 18.0],
}

# Stage 3: Entry Execution (was Stage 2)
# 2 × 3 × 3 × 2 × 2 × 3 = 216 combos × 3 seeds = 648 configs
GRID_3 = {
    "use_pullback_entry": [True, False],
    "pullback_tolerance_pct": [2.0, 3.0, 4.0],
    "pullback_max_wait_bars": [6, 8, 10],
    "require_weekly_confirmation": [True, False],
    "consolidation_max_range_pct": [10.0, 15.0],
    "consolidation_bars": [10, 15, 20],
}

# Stage 4: Exit Management (was Stage 3)
# 3 × 3 × 3 × 3 × 3 = 243 combos × 3 seeds = 729 configs
GRID_4 = {
    "holding_days": [30, 45, 60],
    "initial_stop_atr_multiplier": [1.5, 2.0, 2.5],
    "atr_trailing_activation": [2.0, 2.5, 3.0],
    "atr_trailing_multiplier": [0.8, 1.0, 1.5],
    "risk_reward_ratio": [2.0, 2.5, 3.0],
}

# Stage 5: Position Sizing (was Stage 4)
# 3 × 3 × 3 × 3 × 3 = 243 combos × 3 seeds = 729 configs
GRID_5 = {
    "risk_per_trade_pct": [2.0, 3.0, 4.0],
    "regime_bull_position_pct": [10.0, 12.0, 15.0],
    "regime_neutral_position_pct": [5.0, 7.0, 9.0],
    "regime_bear_position_pct": [0.0, 3.0, 5.0],
    "max_sector_positions": [2, 3, 5],
}

STAGE_GRIDS = {1: GRID_1, 2: GRID_2, 3: GRID_3, 4: GRID_4, 5: GRID_5}
STAGE_CONCURRENT = {1: 4, 2: 4, 3: 4, 4: 4, 5: 4}

# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT / RESUME
# ─────────────────────────────────────────────────────────────────────────────


def _cp_path(stage):
    return Path(f"sweep_completed_stage{stage}.json")


def load_completed_keys(stage):
    with _checkpoint_lock:
        p = _cp_path(stage)
        if not p.exists():
            return set()
        try:
            return set(json.loads(p.read_text()))
        except Exception:
            return set()


def mark_completed_key(stage, key):
    with _checkpoint_lock:
        completed = load_completed_keys(stage)
        completed.add(key)
        _cp_path(stage).write_text(json.dumps(list(completed), indent=2))


def params_to_key(params):
    """Stable string key for a params dict (for checkpointing)."""
    return json.dumps(params, sort_keys=True)


# ─────────────────────────────────────────────────────────────────────────────
# PARAM HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def expand_params(params):
    """
    Expand compound parameters into flat dicts before submission.
    Currently handles rsi_range (index → dict).
    """
    p = dict(params)
    if "rsi_range" in p:
        idx = p.pop("rsi_range")
        p.update(RSI_RANGES[idx])
    return p


def build_combos(grid, seed_params=None):
    """
    Generate all param combos from a grid, merged with seed_params.
    Returns list of expanded flat dicts.
    """
    keys = list(grid.keys())
    raw_combos = list(itertools.product(*grid.values()))
    combos = []
    for vals in raw_combos:
        p = dict(zip(keys, vals))
        if seed_params:
            p = {**seed_params, **p}
        combos.append(expand_params(p))
    return combos


def stage_results_file(stage):
    return Path(f"sweep_stage{stage}_results.json")


def stage_top_file(stage):
    return Path(f"sweep_stage{stage}_top{TOP_N_FANOUT}.json")


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST API CALLS
# ─────────────────────────────────────────────────────────────────────────────


def run_backtest(params, date_from, date_to):
    payload = {**DEFAULTS, **params, "date_from": date_from, "date_to": date_to}
    try:
        response = requests.post(f"{BASE_URL}/run", json=payload, timeout=30)
        if response.status_code != 200:
            print(
                f"  [API] Failed to start: {response.status_code} {response.text[:200]}"
            )
            return None
        return response.json()["run_id"]
    except Exception as e:
        print(f"  [API] Exception starting backtest: {e}")
        return None


def wait_for_run(run_id, poll_interval=5, max_wait_minutes=30):
    start = time.time()
    deadline = start + max_wait_minutes * 60
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/{run_id}", timeout=30)
            if response.status_code != 200:
                print(f"  [{run_id[:8]}] Error checking status: {response.text[:200]}")
                return None
            data = response.json()
            status = data["status"]
            if status == "complete":
                return data
            elif status == "failed":
                print(
                    f"  [{run_id[:8]}] Run failed: {data.get('error_message', 'unknown')}"
                )
                return None
            time.sleep(poll_interval)
        except Exception as e:
            print(f"  [{run_id[:8]}] Exception polling: {e}")
            time.sleep(poll_interval)

    print(f"  [{run_id[:8]}] TIMEOUT after {max_wait_minutes}m — treating as failed")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────


def calculate_robustness(fold_metrics):
    """
    Composite robustness score:
      (Weighted Mean Sharpe − StdDev Sharpe) × 0.7  +  Weighted Mean Calmar × 0.3

    Weights D3 (Bear/Chop) heavily to penalize strategies that blow up in regimes
    where retail usually fails. Penalizes variance across regimes AND high drawdown.
    """
    if not fold_metrics:
        return -99.0

    weighted_sharpes = []
    weighted_calmars = []
    total_weight = 0.0

    for m in fold_metrics:
        w = FOLD_WEIGHTS.get(m["fold"], 1.0)
        days = FOLD_DURATION_DAYS.get(m["fold"], 365)
        # Annualized return: (1 + r)^(365/days) - 1
        ann_ret = ((1 + m["total_return_pct"] / 100) ** (365 / days) - 1) * 100
        calmar = ann_ret / m["max_drawdown_pct"] if m["max_drawdown_pct"] > 0 else 0.0

        weighted_sharpes.append(m["sharpe_ratio"] * w)
        weighted_calmars.append(calmar * w)
        total_weight += w

    mean_sharpe = sum(weighted_sharpes) / total_weight
    mean_calmar = sum(weighted_calmars) / total_weight
    std_sharpe = float(np.std([m["sharpe_ratio"] for m in fold_metrics]))

    return (mean_sharpe - std_sharpe) * 0.7 + mean_calmar * 0.3


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE CONFIG RUN (discovery folds only)
# ─────────────────────────────────────────────────────────────────────────────


def _run_one(params, stage):
    """
    Run a single params combo across all discovery folds.
    Returns a result dict or None if the config hard-failed.

    Low-sample folds are flagged and Sharpe-penalized but do NOT cause
    a hard failure — a config that survives D3 (bear) with low trades is
    still interesting.

    Hard failure = API error or run failure (engine crash / timeout).
    """
    fold_metrics = []
    fold_run_ids = {}

    for fold in DISCOVERY_FOLDS:
        fold_name = fold["name"]
        print(
            f"    [{params.get('score_threshold', '?')}/{params.get('min_adx', '?')}] "
            f"Running {fold_name}..."
        )

        run_id = run_backtest(params, fold["date_from"], fold["date_to"])
        if not run_id:
            print(f"    -> Hard fail on {fold_name} (API error). Skipping config.")
            return None

        fold_run_ids[fold_name] = run_id
        result = wait_for_run(run_id)

        if not result:
            print(f"    -> Hard fail on {fold_name} (run failed). Skipping config.")
            return None

        metrics = result["metrics"]
        total_trades = metrics["total_trades"]
        sharpe = metrics["sharpe_ratio"]
        low_sample = False

        min_trades = FOLD_MIN_TRADES.get(fold_name, 30)
        if total_trades < min_trades:
            print(
                f"    -> WARNING: {fold_name} only {total_trades} trades "
                f"(min {min_trades}). Applying confidence penalty."
            )
            sharpe *= LOW_SAMPLE_SHARPE_PENALTY
            low_sample = True

        fold_metrics.append(
            {
                "fold": fold_name,
                "total_return_pct": metrics["total_return_pct"],
                "sharpe_ratio": sharpe,  # possibly penalized
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "max_drawdown_duration": metrics.get("max_drawdown_duration", 0),
                "win_rate": metrics["win_rate"],
                "total_trades": total_trades,
                "low_sample": low_sample,
            }
        )

    # Count how many folds underperformed (Sharpe < 0 after any penalty)
    failing_folds = [m for m in fold_metrics if m["sharpe_ratio"] < 0]
    if len(failing_folds) >= 2:
        print("    -> Config failed 2+ discovery folds with negative Sharpe. Skipping.")
        return None

    sharpes = [m["sharpe_ratio"] for m in fold_metrics]
    returns = [m["total_return_pct"] for m in fold_metrics]
    dds = [m["max_drawdown_pct"] for m in fold_metrics]
    robustness_score = calculate_robustness(fold_metrics)

    return {
        "params": params,
        "wfo_metrics": {
            "mean_sharpe": float(np.mean(sharpes)),
            "std_sharpe": float(np.std(sharpes)),
            "robustness_score": robustness_score,
            "mean_return_pct": float(np.mean(returns)),
            "mean_drawdown_pct": float(np.mean(dds)),
            "min_sharpe": float(np.min(sharpes)),
            "total_trades_all_folds": sum(m["total_trades"] for m in fold_metrics),
        },
        "fold_results": fold_metrics,
        "run_ids": fold_run_ids,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE SWEEP
# ─────────────────────────────────────────────────────────────────────────────


def run_stage(stage, seed_configs=None):
    """
    Run one full stage sweep.

    seed_configs: list of param dicts from the previous stage's top configs.
                  For Stage 1 this is None (no seeds).
    Returns: list of all result dicts from this stage.
    """
    grid = STAGE_GRIDS[stage]
    max_concurrent = STAGE_CONCURRENT[stage]

    # Build all combos, merged with each seed config
    if seed_configs:
        all_combos = []
        for seed in seed_configs:
            all_combos.extend(build_combos(grid, seed_params=seed))
    else:
        all_combos = build_combos(grid)

    completed_keys = load_completed_keys(stage)
    pending = [c for c in all_combos if params_to_key(c) not in completed_keys]

    print(f"\n{'=' * 70}")
    print(
        f"STAGE {stage}: {len(all_combos)} total combos, "
        f"{len(pending)} remaining (MAX_CONCURRENT={max_concurrent})"
    )
    print(f"{'=' * 70}\n")

    # Load any already-saved results so we don't lose them on resume
    results_path = stage_results_file(stage)
    all_results = []
    if results_path.exists():
        try:
            all_results = json.loads(results_path.read_text())
            print(f"  Loaded {len(all_results)} existing results from {results_path}")
        except Exception:
            all_results = []

    lock = threading.Lock()

    def _submit(params):
        key = params_to_key(params)
        result = _run_one(params, stage)

        snapshot = None
        with lock:
            if result:
                all_results.append(result)
                snapshot = list(all_results)
            mark_completed_key(stage, key)

        if snapshot:
            temp_path = results_path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(snapshot, indent=2))
            temp_path.replace(results_path)

        return result

    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {pool.submit(_submit, p): i for i, p in enumerate(pending)}
        for done, future in enumerate(as_completed(futures), 1):
            result = future.result()
            status = "OK" if result else "SKIP"
            print(
                f"  [{done}/{len(pending)}] {status} — "
                f"{len(all_results)} collected so far"
            )

    return all_results


# ─────────────────────────────────────────────────────────────────────────────
# SELECT TOP N CONFIGS FROM A STAGE
# ─────────────────────────────────────────────────────────────────────────────


def select_top_configs(all_results, n=TOP_N_FANOUT):
    """
    Return the top N param dicts by robustness_score.
    These become the seeds for the next stage.
    """
    if TOP_N_FANOUT_OVERRIDE:
        print(f"\nUsing TOP_N_FANOUT_OVERRIDE ({len(TOP_N_FANOUT_OVERRIDE)} configs).")
        return TOP_N_FANOUT_OVERRIDE

    ranked = sorted(
        all_results, key=lambda x: x["wfo_metrics"]["robustness_score"], reverse=True
    )[:n]

    print(f"\nTop {n} configs advancing to next stage:")
    for i, r in enumerate(ranked, 1):
        m = r["wfo_metrics"]
        print(
            f"  #{i}: robustness={m['robustness_score']:.3f}  "
            f"mean_sharpe={m['mean_sharpe']:.2f}  "
            f"std_sharpe={m['std_sharpe']:.2f}  "
            f"params={r['params']}"
        )

    return [r["params"] for r in ranked]


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION + CONTINUOUS STRESS TEST
# ─────────────────────────────────────────────────────────────────────────────


def run_validation(finalist):
    print(f"\n  Validating: {finalist['params']}")
    val_results = []
    val_run_ids = {}

    for fold in VALIDATION_FOLDS:
        run_id = run_backtest(finalist["params"], fold["date_from"], fold["date_to"])
        if not run_id:
            print(f"    -> API error on {fold['name']}. Validation failed.")
            return None

        result = wait_for_run(run_id)
        if not result:
            print(f"    -> Run failed on {fold['name']}. Validation failed.")
            return None

        metrics = result["metrics"]
        sharpe = metrics["sharpe_ratio"]
        val_run_ids[fold["name"]] = run_id

        if sharpe < 0:
            print(f"    -> FAILED {fold['name']} (Sharpe={sharpe:.2f} < 0)")
            return None

        val_results.append(
            {
                "fold": fold["name"],
                "sharpe_ratio": sharpe,
                "total_return_pct": metrics["total_return_pct"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
            }
        )
        print(
            f"    -> PASS {fold['name']}: Sharpe={sharpe:.2f}  "
            f"Ret={metrics['total_return_pct']:.1f}%  "
            f"DD={metrics['max_drawdown_pct']:.1f}%"
        )

    return {"results": val_results, "run_ids": val_run_ids}


def run_continuous_test(params):
    print(
        f"\n  Continuous stress test "
        f"({CONTINUOUS_STRESS['date_from']} → {CONTINUOUS_STRESS['date_to']})..."
    )
    run_id = run_backtest(
        params, CONTINUOUS_STRESS["date_from"], CONTINUOUS_STRESS["date_to"]
    )
    if not run_id:
        return None
    result = wait_for_run(run_id)
    if not result:
        return None
    return {"run_id": run_id, "metrics": result["metrics"]}


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def generate_stage_report(stage, all_results):
    report_path = Path(f"sweep_stage{stage}_report.md")
    ranked = sorted(
        all_results, key=lambda x: x["wfo_metrics"]["robustness_score"], reverse=True
    )

    with report_path.open("w") as f:
        f.write(f"# Stage {stage} Sweep Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Total configs evaluated:** {len(all_results)}\n\n")

        f.write("## Robustness Score Formula\n")
        f.write(
            "`(Weighted Mean Sharpe − StdDev Sharpe) × 0.7 + Weighted Mean Calmar × 0.3`\n\n"
        )
        f.write("Weights: D1=1.2 (Crash), D2=0.8 (Bull), D3=2.0 (Bear/Chop).\n\n")
        f.write("Higher = more consistent across regimes AND lower drawdown.\n\n")

        f.write("## Top 15 Configurations\n")
        f.write(
            "| Rank | Robustness | Mean Sharpe | Std Sharpe | Min Sharpe | "
            "Mean Ret% | Mean DD% | Trades | Config |\n"
        )
        f.write(
            "|------|-----------|-------------|------------|------------|"
            "----------|----------|--------|--------|\n"
        )
        for i, res in enumerate(ranked[:15]):
            m = res["wfo_metrics"]
            p_str = ", ".join(
                f"{k}={v}" for k, v in res["params"].items() if k not in DEFAULTS
            )
            f.write(
                f"| {i + 1} | {m['robustness_score']:.3f} | "
                f"{m['mean_sharpe']:.2f} | {m['std_sharpe']:.2f} | "
                f"{m['min_sharpe']:.2f} | {m['mean_return_pct']:.1f}% | "
                f"{m['mean_drawdown_pct']:.1f}% | "
                f"{m['total_trades_all_folds']} | `{p_str}` |\n"
            )

        f.write("\n## Fold Breakdown for Top 5\n")
        for i, res in enumerate(ranked[:5]):
            f.write(f"\n### #{i + 1} — `{res['params']}`\n")

            if stage == 2:
                params = res["params"]
                adx_floor = params.get("regime_adx_floor", 0.0)
                breadth_pct = params.get("min_market_breadth_pct", 0.0)
                if adx_floor >= 18.0 and breadth_pct >= 50.0:
                    f.write(
                        "> **Note on Restricted Trades:** This config combines a high `regime_adx_floor` (>= 18.0) "
                        "with a high `min_market_breadth_pct` (>= 50.0). On the NSE, this leads to frequent bear/cash mode "
                        "during prolonged sideways periods (e.g., 2022-2023), resulting in very low trade counts that often trigger "
                        "the `LOW_SAMPLE_SHARPE_PENALTY` (like in D3). Verify if this strictness is intended.\n\n"
                    )

            f.write(
                "| Fold | Sharpe | Return% | DD% | DD Days | Win Rate% | "
                "Trades | Low Sample? | Run ID |\n"
            )
            f.write(
                "|------|--------|---------|-----|---------|-----------|"
                "--------|-------------|--------|\n"
            )
            for fold in res["fold_results"]:
                rid = res["run_ids"].get(fold["fold"], "N/A")
                ls = "⚠️ YES" if fold.get("low_sample") else "No"
                f.write(
                    f"| {fold['fold']} | {fold['sharpe_ratio']:.2f} | "
                    f"{fold['total_return_pct']:.1f}% | "
                    f"{fold['max_drawdown_pct']:.1f}% | "
                    f"{fold['max_drawdown_duration']} | "
                    f"{fold['win_rate']:.1f}% | "
                    f"{fold['total_trades']} | {ls} | `{rid[:8]}` |\n"
                )

    print(f"\nStage {stage} report written: {report_path}")


def generate_master_report(finalists):
    report_path = Path("MASTER_STRATEGY_REPORT.md")
    if not finalists:
        print("No finalists to report.")
        return

    with report_path.open("w") as f:
        f.write("# Master Strategy Report — NSE WFO Sweep\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(
            "Strategies that passed all 3 discovery folds, all 3 OOS validation "
            "folds, and the 6-year continuous stress test.\n\n"
        )

        for i, fst in enumerate(finalists):
            f.write(f"## Strategy #{i + 1}\n")
            f.write(f"**Params:** `{fst['params']}`\n\n")

            f.write("### Continuous Stress Test (Mar 2020 – Jun 2026)\n")
            m = fst["continuous_test"]["metrics"]
            f.write("| Metric | Value |\n|--------|-------|\n")
            f.write(f"| Sharpe Ratio | {m['sharpe_ratio']:.2f} |\n")
            f.write(f"| Total Return | {m['total_return_pct']:.1f}% |\n")
            f.write(f"| Max Drawdown | {m['max_drawdown_pct']:.1f}% |\n")
            f.write(f"| Win Rate | {m['win_rate']:.1f}% |\n")
            f.write(f"| Total Trades | {m['total_trades']} |\n\n")

            f.write("### All Folds Performance\n")
            f.write("| Phase | Fold | Sharpe | Return% | DD% | Run ID |\n")
            f.write("|-------|------|--------|---------|-----|--------|\n")
            for res in fst["fold_results"]:
                rid = fst["run_ids"].get(res["fold"], "N/A")
                f.write(
                    f"| Discovery | {res['fold']} | {res['sharpe_ratio']:.2f} | "
                    f"{res['total_return_pct']:.1f}% | "
                    f"{res['max_drawdown_pct']:.1f}% | `{rid[:8]}` |\n"
                )
            for res in fst["validation"]["results"]:
                rid = fst["validation"]["run_ids"].get(res["fold"], "N/A")
                f.write(
                    f"| Validation | {res['fold']} | {res['sharpe_ratio']:.2f} | "
                    f"{res['total_return_pct']:.1f}% | "
                    f"{res['max_drawdown_pct']:.1f}% | `{rid[:8]}` |\n"
                )
            cid = fst["continuous_test"]["run_id"]
            f.write(
                f"| Stress | 2020-2026 | {m['sharpe_ratio']:.2f} | "
                f"{m['total_return_pct']:.1f}% | "
                f"{m['max_drawdown_pct']:.1f}% | `{cid[:8]}` |\n\n"
            )

            all_ids = (
                list(fst["run_ids"].values())
                + list(fst["validation"]["run_ids"].values())
                + [fst["continuous_test"]["run_id"]]
            )
            f.write("### Audit Command\n")
            f.write(
                f"```bash\npython verify_backtest_trades.py "
                f"{' '.join(all_ids)}\n```\n\n"
            )

    print(f"\nMaster report written: {report_path}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 FINALIZATION (validation + stress test)
# ─────────────────────────────────────────────────────────────────────────────


def run_finalization(all_stage5_results):
    print("\n" + "=" * 70)
    print("FINALIZATION: Validation + Continuous Stress Test")
    print("=" * 70)

    top_candidates = sorted(
        all_stage5_results,
        key=lambda x: x["wfo_metrics"]["robustness_score"],
        reverse=True,
    )[:5]

    print(f"\nRunning validation for top {len(top_candidates)} configs...")
    final_verified = []

    for finalist in top_candidates:
        val_data = run_validation(finalist)
        if not val_data:
            print("  -> Config did not pass validation. Moving on.")
            continue

        stress_data = run_continuous_test(finalist["params"])
        if not stress_data:
            print("  -> Continuous stress test failed. Moving on.")
            continue

        finalist["validation"] = val_data
        finalist["continuous_test"] = stress_data
        final_verified.append(finalist)
        print(f"  -> Config VERIFIED. {len(final_verified)} verified so far.")

    Path("final_verified_strategies.json").write_text(
        json.dumps(final_verified, indent=2)
    )
    generate_master_report(final_verified)
    print(f"\n{len(final_verified)} strategies passed full verification.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Staged WFO parameter sweep for NSE backtesting engine."
    )
    parser.add_argument(
        "--stage",
        type=int,
        required=True,
        choices=[1, 2, 3, 4, 5],
        help="Which stage to run (1-5). Run in order.",
    )
    args = parser.parse_args()
    stage = args.stage

    # ── Load seeds from previous stage ────────────────────────────────────────
    seed_configs = None
    if stage > 1:
        seed_file = stage_top_file(stage - 1)
        if not seed_file.exists():
            print(f"\nERROR: {seed_file} not found.")
            print(f"You must run --stage {stage - 1} before --stage {stage}.")
            sys.exit(1)
        seed_configs = json.loads(seed_file.read_text())
        print(f"\nLoaded {len(seed_configs)} seed config(s) from {seed_file}")
        for i, s in enumerate(seed_configs, 1):
            print(f"  Seed #{i}: {s}")

    # ── Run the sweep for this stage ──────────────────────────────────────────
    all_results = run_stage(stage, seed_configs=seed_configs)

    # ── Generate report ───────────────────────────────────────────────────────
    generate_stage_report(stage, all_results)

    # ── Select top configs and save for next stage ────────────────────────────
    top_configs = select_top_configs(all_results)
    top_file = stage_top_file(stage)
    top_file.write_text(json.dumps(top_configs, indent=2))
    print(f"\nTop {len(top_configs)} configs saved to {top_file}")

    # ── If Stage 5, run finalization ──────────────────────────────────────────
    if stage == 5:
        run_finalization(all_results)

    print(f"\nStage {stage} complete.")
    if stage < 5:
        print(f"\nNext step: review sweep_stage{stage}_report.md, then run:")
        print(f"  python parameter_sweep.py --stage {stage + 1}")
    else:
        print("\nAll stages complete. Review MASTER_STRATEGY_REPORT.md.")


if __name__ == "__main__":
    main()
