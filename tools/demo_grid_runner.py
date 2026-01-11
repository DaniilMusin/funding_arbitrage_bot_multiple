#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import itertools
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except Exception as exc:
    print(f"Missing dependency for YAML parsing: {exc}")
    sys.exit(1)


DEFAULT_SCRIPT = "v2_funding_rate_arb.py"
DEFAULT_BASE_CONFIG = "conf/scripts/v2_funding_rate_arb.yml"
DEFAULT_GRID_DIR = "conf/scripts/demo_grid"
DEFAULT_RESULTS_DIR = "logs/demo_grid"

DEFAULT_GRID = {
    "min_funding_rate_profitability": [0.0006, 0.0008, 0.001, 0.0012, 0.0015, 0.002, 0.0025],
    "profitability_to_take_profit": [0.004, 0.006, 0.008, 0.01, 0.015, 0.02],
    "funding_rate_diff_stop_loss": [-0.0003, -0.0005, -0.0008, -0.001, -0.0015, -0.002],
    "max_slippage_pct": [0.002, 0.003, 0.004, 0.005, 0.0075],
    "min_order_book_depth_multiplier": [2.0, 2.5, 3.0, 3.5, 4.0],
    "min_time_to_next_funding_seconds": [120, 240, 300, 600, 900],
    "position_size_quote_pct": [0.25, 0.5, 0.75, 1.0],
    "max_positions_per_connector": [1, 2, 3],
    "leverage": [3, 5, 7, 10],
}


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def dump_yaml(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def param_hash(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


def generate_combinations(grid: dict):
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo))


def read_metrics(metrics_file: str) -> dict | None:
    if not os.path.isfile(metrics_file):
        return None
    last_row = None
    try:
        with open(metrics_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                last_row = row
    except Exception:
        return None
    if not last_row:
        return None
    try:
        return {
            "total_pnl": float(last_row.get("total_pnl", 0)),
            "max_drawdown_pct": float(last_row.get("max_drawdown_pct", 0)),
            "max_drawdown": float(last_row.get("max_drawdown", 0)),
            "equity": float(last_row.get("equity", 0)),
        }
    except Exception:
        return None


def select_best(results: list[dict]) -> dict | None:
    valid = [r for r in results if r.get("metrics") is not None]
    if not valid:
        return None
    return sorted(
        valid,
        key=lambda r: (-r["metrics"]["total_pnl"], r["metrics"]["max_drawdown_pct"])
    )[0]


def build_demo_config(base_config: dict, params: dict, run_id: str, metrics_file: str, interval: int) -> dict:
    cfg = dict(base_config)
    cfg.update(params)
    cfg["demo_mode"] = True
    cfg["demo_run_id"] = run_id
    cfg["demo_metrics_enabled"] = True
    cfg["demo_metrics_file"] = metrics_file
    cfg["demo_metrics_interval_seconds"] = interval
    return cfg


def run_cmd(cmd: list[str], cwd: str) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=cwd)


def stop_process(proc: subprocess.Popen, timeout: int = 20):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def validate_base_config(base_config: dict, parallel: int):
    connectors = base_config.get("connectors") or []
    tokens = base_config.get("tokens") or []
    if len(connectors) < 2:
        raise ValueError("Base config needs at least 2 connectors.")
    if len(tokens) == 0:
        raise ValueError("Base config needs at least 1 token.")
    if not base_config.get("position_validation_enabled", True):
        print("Warning: position_validation_enabled is False in base config.")
    if not base_config.get("emergency_close_on_imbalance", True):
        print("Warning: emergency_close_on_imbalance is False in base config.")
    if len(tokens) > 60 and parallel >= 4:
        print("Warning: large token set with 4 parallel demos may hit rate limits.")


def main():
    parser = argparse.ArgumentParser(description="Run demo parameter grid in parallel and auto-apply best weekly.")
    parser.add_argument("--script", default=DEFAULT_SCRIPT)
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--grid-config", default="")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--run-days", type=int, default=7)
    parser.add_argument("--metrics-interval", type=int, default=60)
    parser.add_argument("--password", default="")
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--grid-dir", default=DEFAULT_GRID_DIR)
    parser.add_argument("--cycles", type=int, default=0, help="0 = infinite")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-apply-best", action="store_true", help="Do not auto-apply best params to base config.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if os.sep in args.script or (os.altsep and os.altsep in args.script):
        script_path = str(repo_root / args.script)
        script_name = os.path.basename(args.script)
    else:
        script_path = str(repo_root / "scripts" / args.script)
        script_name = args.script
    base_config_path = str(repo_root / args.base_config)

    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script file not found: {script_path}")
    if not os.path.isfile(base_config_path):
        raise FileNotFoundError(f"Base config not found: {base_config_path}")

    base_config = load_yaml(base_config_path)
    validate_base_config(base_config, args.parallel)

    grid = DEFAULT_GRID
    if args.grid_config:
        grid = load_yaml(args.grid_config)

    combos = list(generate_combinations(grid))
    if not combos:
        raise ValueError("Grid is empty.")

    grid_dir_abs = repo_root / args.grid_dir
    conf_scripts_root = repo_root / "conf" / "scripts"
    try:
        grid_dir_rel = os.path.relpath(grid_dir_abs, conf_scripts_root)
    except ValueError:
        grid_dir_rel = "demo_grid"
    if grid_dir_rel.startswith(".."):
        grid_dir_abs = conf_scripts_root / "demo_grid"
        grid_dir_rel = "demo_grid"
    ensure_dir(str(grid_dir_abs))
    ensure_dir(str(repo_root / args.results_dir))

    rng = random.Random(args.seed)
    used = set()

    cycle = 0
    while True:
        cycle += 1
        if args.cycles and cycle > args.cycles:
            break

        rng.shuffle(combos)
        selected = []
        for params in combos:
            h = param_hash(params)
            if h in used:
                continue
            selected.append(params)
            used.add(h)
            if len(selected) >= args.parallel:
                break

        if len(selected) < args.parallel:
            used.clear()
            rng.shuffle(combos)
            selected = combos[:args.parallel]

        run_ts = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        runs = []
        for idx, params in enumerate(selected):
            run_id = f"{run_ts}_{idx+1}"
            metrics_file = str(repo_root / args.results_dir / f"{run_id}.csv")
            cfg = build_demo_config(base_config, params, run_id, metrics_file, args.metrics_interval)
            cfg_name = f"demo_grid_{run_id}.yml"
            cfg_path = str(grid_dir_abs / cfg_name)
            dump_yaml(cfg_path, cfg)

            cfg_arg = os.path.join(grid_dir_rel, cfg_name) if grid_dir_rel != "." else cfg_name
            cmd = [sys.executable, "bin/hummingbot_quickstart.py", "-f", script_name, "-c", cfg_arg]
            if args.password:
                cmd += ["-p", args.password]

            proc = run_cmd(cmd, cwd=str(repo_root))
            runs.append({
                "run_id": run_id,
                "params": params,
                "metrics_file": metrics_file,
                "config_file": cfg_path,
                "process": proc,
            })

        end_time = time.time() + (args.run_days * 86400)
        while time.time() < end_time:
            for run in runs:
                proc = run["process"]
                if proc.poll() is not None:
                    cfg_arg = os.path.join(grid_dir_rel, os.path.basename(run["config_file"])) if grid_dir_rel != "." else os.path.basename(run["config_file"])
                    cmd = [sys.executable, "bin/hummingbot_quickstart.py", "-f", script_name, "-c", cfg_arg]
                    if args.password:
                        cmd += ["-p", args.password]
                    run["process"] = run_cmd(cmd, cwd=str(repo_root))
            time.sleep(30)

        for run in runs:
            stop_process(run["process"])

        results = []
        for run in runs:
            metrics = read_metrics(run["metrics_file"])
            results.append({
                "run_id": run["run_id"],
                "params": run["params"],
                "metrics": metrics,
                "metrics_file": run["metrics_file"],
            })

        best = select_best(results)
        summary_name = f"weekly_results_{run_ts}.json"
        summary_path = str(repo_root / args.results_dir / summary_name)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"runs": results, "best": best}, f, indent=2)

        if best and not args.no_apply_best:
            new_config = dict(base_config)
            new_config.update(best["params"])
            dump_yaml(base_config_path, new_config)
            base_config = new_config


if __name__ == "__main__":
    main()
