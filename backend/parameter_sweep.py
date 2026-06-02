import itertools
import json
import time
from datetime import datetime

import requests

# Configuration
BASE_URL = "http://localhost:8000/api/backtest"
REPORT_FILE = "sweep_report.md"
RESULTS_FILE = "sweep_results.json"

# Parameters to Sweep
GRID = {
    "score_threshold": [55.0, 65.0],
    "holding_days": [30, 45],
    "ema_weight": [25.0, 30.0],
    "macd_weight": [15.0, 25.0],
    "rsi_weight": [15.0, 25.0],
    "volume_weight": [15.0, 25.0],
    "ema200_weight": [5.0, 10.0],
}

# Fixed Parameters
DEFAULTS = {
    "date_from": "2022-01-01",
    "date_to": "2024-01-01",
    "symbol_limit": 100,  # Keep it small for the sweep
    "use_regime_filter": True,
    "starting_capital": 1000000.0,
    "position_size": 20000.0,
    "use_volatility_sizing": True,
}


def run_backtest(params):
    payload = {**DEFAULTS, **params}
    response = requests.post(f"{BASE_URL}/run", json=payload)
    if response.status_code != 200:
        print(f"Failed to start backtest: {response.text}")
        return None
    return response.json()["run_id"]


def wait_for_run(run_id):
    print(f"Waiting for run {run_id}...", end="", flush=True)
    while True:
        response = requests.get(f"{BASE_URL}/{run_id}")
        if response.status_code != 200:
            print(f"\nError checking status: {response.text}")
            return None

        data = response.json()
        status = data["status"]
        if status == "complete":
            print(" Done.")
            return data
        elif status == "failed":
            print(f" Failed: {data.get('error_message')}")
            return None

        print(".", end="", flush=True)
        time.sleep(5)


def main():
    keys = GRID.keys()
    combinations = list(itertools.product(*GRID.values()))
    print(f"Starting sweep with {len(combinations)} combinations...")

    all_results = []

    for i, values in enumerate(combinations):
        params = dict(zip(keys, values))
        print(f"\n[{i + 1}/{len(combinations)}] Testing: {params}")

        run_id = run_backtest(params)
        if run_id:
            result = wait_for_run(run_id)
            if result:
                # Store params + metrics
                summary = {
                    "params": params,
                    "metrics": {
                        "total_return_pct": result["total_return_pct"],
                        "sharpe_ratio": result["sharpe_ratio"],
                        "win_rate": result["win_rate"],
                        "max_drawdown_pct": result["max_drawdown_pct"],
                        "total_trades": result["total_trades"],
                        "profit_factor": result["profit_factor"],
                        "expectancy": result["expectancy"],
                    },
                }
                all_results.append(summary)

                # Intermediate save
                with open(RESULTS_FILE, "w") as f:
                    json.dump(all_results, f, indent=2)

    # Generate Report
    generate_report(all_results)


def generate_report(results):
    if not results:
        print("No results to report.")
        return

    # Sort by Sharpe Ratio (desc) or Total Return
    best_sharpe = sorted(
        results, key=lambda x: x["metrics"]["sharpe_ratio"], reverse=True
    )
    best_return = sorted(
        results, key=lambda x: x["metrics"]["total_return_pct"], reverse=True
    )

    with open(REPORT_FILE, "w") as f:
        f.write("# Backtest Parameter Sweep Report\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Top 5 Configurations (by Sharpe Ratio)\n")
        f.write("| Rank | Sharpe | Return % | DD % | Win Rate % | Trades | Config |\n")
        f.write("|------|--------|----------|------|------------|--------|--------|\n")
        for i, res in enumerate(best_sharpe[:5]):
            m = res["metrics"]
            p = res["params"]
            p_str = f"Score: {p['score_threshold']}, Hold: {p['holding_days']}, Consol: {p['require_consolidation']}, Pullback: {p['use_pullback_entry']}"
            f.write(
                f"| {i + 1} | {m['sharpe_ratio']:.2f} | {m['total_return_pct']:.2f}% | {m['max_drawdown_pct']:.2f}% | {m['win_rate']:.2f}% | {m['total_trades']} | {p_str} |\n"
            )

        f.write("\n## Top 5 Configurations (by Total Return)\n")
        f.write("| Rank | Return % | Sharpe | DD % | Win Rate % | Trades | Config |\n")
        f.write("|------|----------|--------|------|------------|--------|--------|\n")
        for i, res in enumerate(best_return[:5]):
            m = res["metrics"]
            p = res["params"]
            p_str = f"Score: {p['score_threshold']}, Hold: {p['holding_days']}, Consol: {p['require_consolidation']}, Pullback: {p['use_pullback_entry']}"
            f.write(
                f"| {i + 1} | {m['total_return_pct']:.2f}% | {m['sharpe_ratio']:.2f} | {m['max_drawdown_pct']:.2f}% | {m['win_rate']:.2f}% | {m['total_trades']} | {p_str} |\n"
            )

    print(f"\nReport generated: {REPORT_FILE}")


if __name__ == "__main__":
    main()
