import itertools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import requests

# Configuration
MAX_CONCURRENT = 4
BASE_URL = "http://localhost:8000/api/backtest"
REPORT_FILE = "sweep_report.md"
RESULTS_FILE = "sweep_results.json"

# Parameters to Sweep (Discovery Grid)
GRID = {
    "score_threshold": [55.0, 60.0, 65.0],
    "holding_days": [30, 45],
    "ema_weight": [25.0, 30.0],
    "macd_weight": [15.0],
    "rsi_weight": [15.0],
    "volume_weight": [15.0],
    "ema200_weight": [10.0],
}

# Stage 1 Folds (In-Sample Discovery)
DISCOVERY_FOLDS = [
    {"name": "Fold 1 (Crash)", "date_from": "2020-02-01", "date_to": "2020-04-30"},
    {"name": "Fold 2 (Chop)", "date_from": "2021-10-19", "date_to": "2023-03-20"},
    {"name": "Fold 3 (Bull)", "date_from": "2023-03-21", "date_to": "2024-02-01"},
]

# Stage 2 Folds (Out-of-Sample Validation)
VALIDATION_FOLDS = [
    {"name": "Fold 4 (Recovery)", "date_from": "2020-05-01", "date_to": "2021-10-18"},
    {"name": "Fold 5 (Post-Bull)", "date_from": "2024-02-02", "date_to": "2025-06-01"},
    {"name": "Fold 6 (Recent)", "date_from": "2025-06-02", "date_to": "2026-06-09"},
]

# Fixed Parameters
DEFAULTS = {
    "symbol_limit": None,  # Trigger full universe
    "use_regime_filter": True,
    "starting_capital": 1000000.0,
    "position_size": 20000.0,
    "use_volatility_sizing": True,
}


def run_backtest(params, date_from, date_to):
    payload = {**DEFAULTS, **params, "date_from": date_from, "date_to": date_to}
    try:
        response = requests.post(f"{BASE_URL}/run", json=payload)
        if response.status_code != 200:
            print(f"Failed to start backtest: {response.text}")
            return None
        return response.json()["run_id"]
    except Exception as e:
        print(f"Exception starting backtest: {e}")
        return None


def wait_for_run(run_id):
    print(f"[{run_id}] Waiting for run to complete...")
    while True:
        try:
            response = requests.get(f"{BASE_URL}/{run_id}")
            if response.status_code != 200:
                print(f"[{run_id}] Error checking status: {response.text}")
                return None

            data = response.json()
            status = data["status"]
            if status == "complete":
                print(f"[{run_id}] Done.")
                return data
            elif status == "failed":
                print(f"[{run_id}] Failed: {data.get('error_message')}")
                return None

            time.sleep(5)
        except Exception as e:
            print(f"[{run_id}] Exception checking status: {e}")
            return None


def calculate_robustness(fold_metrics):
    sharpes = [m["sharpe_ratio"] for m in fold_metrics]
    if not sharpes:
        return -99.0

    mean_sharpe = float(np.mean(sharpes))
    std_sharpe = float(np.std(sharpes))

    # CLB Robustness = Mean - Std
    return mean_sharpe - std_sharpe


def _run_one(params):
    fold_metrics = []
    fold_run_ids = {}
    config_failed = False

    for fold in DISCOVERY_FOLDS:
        print(f"  -> Running {fold['name']} with params {params}")
        run_id = run_backtest(params, fold["date_from"], fold["date_to"])

        if not run_id:
            config_failed = True
            break

        fold_run_ids[fold["name"]] = run_id
        result = wait_for_run(run_id)

        if not result:
            config_failed = True
            break

        fold_metrics.append(
            {
                "fold": fold["name"],
                "total_return_pct": result["total_return_pct"],
                "sharpe_ratio": result["sharpe_ratio"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "max_drawdown_duration": result.get("max_drawdown_duration", 0),
                "win_rate": result["win_rate"],
                "total_trades": result["total_trades"],
            }
        )

    if config_failed:
        print(f"  -> Config {params} failed on one or more folds. Skipping.")
        return None

    # Calculate WFO Aggregate Metrics
    sharpes = [m["sharpe_ratio"] for m in fold_metrics]
    returns = [m["total_return_pct"] for m in fold_metrics]
    dds = [m["max_drawdown_pct"] for m in fold_metrics]

    mean_sharpe = float(np.mean(sharpes))
    std_sharpe = float(np.std(sharpes))
    robustness_score = calculate_robustness(fold_metrics)

    summary = {
        "params": params,
        "wfo_metrics": {
            "mean_sharpe": mean_sharpe,
            "std_sharpe": std_sharpe,
            "robustness_score": robustness_score,
            "mean_return_pct": float(np.mean(returns)),
            "mean_drawdown_pct": float(np.mean(dds)),
            "min_sharpe": float(np.min(sharpes)),
            "total_trades_all_folds": sum(m["total_trades"] for m in fold_metrics),
        },
        "fold_results": fold_metrics,
        "run_ids": fold_run_ids,  # Persist run_ids for analysis
    }
    return summary


def run_validation(finalist):
    print(f"\n--- VALIDATING CONFIG: {finalist['params']} ---")
    val_results = []
    val_run_ids = {}

    for fold in VALIDATION_FOLDS:
        run_id = run_backtest(finalist["params"], fold["date_from"], fold["date_to"])
        if not run_id:
            return None

        result = wait_for_run(run_id)
        if not result:
            return None

        val_run_ids[fold["name"]] = run_id
        val_results.append(
            {
                "fold": fold["name"],
                "sharpe_ratio": result["sharpe_ratio"],
                "total_return_pct": result["total_return_pct"],
            }
        )

        if result["sharpe_ratio"] < 0:
            print(f"  FAILED Validation on {fold['name']} (Sharpe < 0)")
            return None

    return {"results": val_results, "run_ids": val_run_ids}


def run_continuous_test(params):
    print("\n--- RUNNING CONTINUOUS STRESS TEST (2020-2026) ---")
    run_id = run_backtest(params, "2020-02-01", "2026-06-09")
    if not run_id:
        return None

    result = wait_for_run(run_id)
    return {"run_id": run_id, "metrics": result} if result else None


def generate_master_report(finalists):
    """Stub for Task 4"""
    print(f"Generating master report for {len(finalists)} finalists...")
    with open("MASTER_STRATEGY_REPORT.md", "w") as f:
        f.write("# Master Strategy Audit Report (STUB)\n")


def main():
    keys = list(GRID.keys())
    combos = list(itertools.product(*GRID.values()))
    print(f"Sweep: {len(combos)} combinations, {MAX_CONCURRENT} concurrent\n")

    all_results: list[dict] = []
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {
            pool.submit(_run_one, dict(zip(keys, v))): i for i, v in enumerate(combos)
        }
        for done, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                with lock:
                    all_results.append(result)
                    with open(RESULTS_FILE, "w") as f:
                        json.dump(all_results, f, indent=2)
            print(f"[{done}/{len(combos)}] done, {len(all_results)} collected")

    # Stage 2: Validation of top candidates
    print("\n--- STAGE 2: VALIDATION ---")
    top_candidates = sorted(
        all_results, key=lambda x: x["wfo_metrics"]["robustness_score"], reverse=True
    )[:5]

    final_verified = []
    for finalist in top_candidates:
        val_data = run_validation(finalist)
        if val_data:
            stress_data = run_continuous_test(finalist["params"])
            if stress_data:
                finalist["validation"] = val_data
                finalist["continuous_test"] = stress_data
                final_verified.append(finalist)

    # Save final results and generate report
    with open("final_verified_strategies.json", "w") as f:
        json.dump(final_verified, f, indent=2)

    generate_master_report(final_verified)
    generate_report(all_results)


def generate_report(results):
    if not results:
        print("No results to report.")
        return

    # Sort by Robustness Score (desc)
    best_robustness = sorted(
        results, key=lambda x: x["wfo_metrics"]["robustness_score"], reverse=True
    )

    with open(REPORT_FILE, "w") as f:
        f.write("# Regime-Balanced WFO Parameter Sweep Report\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Explanation of Metrics\n")
        f.write(
            "- **Robustness Score**: `Mean(Sharpe) / (StdDev(Sharpe) + 0.1)`. Higher is better. Indicates consistent performance across different market regimes.\n"
        )
        f.write("- **Folds**: Tested across 3 regimes (Bull, Chop/Bear, Bull).\n\n")

        f.write("## Top 10 Configurations (by Robustness Score)\n")
        f.write(
            "| Rank | Robustness | Mean Sharpe | Min Sharpe | Mean Ret % | Mean DD % | Trades | Config | Run IDs (for verify script) |\n"
        )
        f.write(
            "|------|------------|-------------|------------|------------|-----------|--------|--------|-----------------------------|\n"
        )
        for i, res in enumerate(best_robustness[:10]):
            m = res["wfo_metrics"]
            p = res["params"]
            r_ids = res.get("run_ids", {})

            p_str = ", ".join([f"{k}:{v}" for k, v in p.items()])
            # Format run IDs concisely
            r_str = "<br>".join([f"{k}: `{v[:8]}...`" for k, v in r_ids.items()])

            f.write(
                f"| {i + 1} | {m['robustness_score']:.2f} | {m['mean_sharpe']:.2f} | {m['min_sharpe']:.2f} | {m['mean_return_pct']:.2f}% | {m['mean_drawdown_pct']:.2f}% | {m['total_trades_all_folds']} | {p_str} | {r_str} |\n"
            )

        f.write("\n## Detailed Fold Breakdown for Top 3\n")
        for i, res in enumerate(best_robustness[:3]):
            f.write(f"### #{i + 1} Config\n")
            f.write(f"`{res['params']}`\n\n")
            f.write(
                "| Fold | Sharpe | Return % | DD % | DD Days | Win Rate % | Trades | Run ID |\n"
            )
            f.write(
                "|------|--------|----------|------|---------|------------|--------|--------|\n"
            )
            for fold in res["fold_results"]:
                r_id = res["run_ids"].get(fold["fold"], "N/A")
                f.write(
                    f"| {fold['fold']} | {fold['sharpe_ratio']:.2f} | {fold['total_return_pct']:.2f}% | {fold['max_drawdown_pct']:.2f}% | {fold['max_drawdown_duration']} | {fold['win_rate']:.2f}% | {fold['total_trades']} | `{r_id}` |\n"
                )
            f.write("\n")

    print(f"\nReport generated: {REPORT_FILE}")
    print(f"Results with run_ids saved to: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
