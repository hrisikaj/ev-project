#!/usr/bin/env python3
"""
Run normal, crash, and partition load-generator scenarios.

The runner invokes the existing scripts/load_generator.py with --csv and --send.
It saves one stdout/stderr log per scenario and a summary CSV.

This does not manufacture per-request outcome records: the supplied load
generator currently prints submission results but does not write an outcome CSV.

Partition limitation:
The current city server does not read config/partitions.json, so the partition
scenario records the partition state but does not actually block inter-city
requests until the server is updated.

Crash configuration:
Pass --pid-file and --start-command for the CockroachDB node to crash.
Store deletion is opt-in and requires BOTH --wipe-store and --confirm-wipe.
"""

import argparse
import csv
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INJECTOR = ROOT / "scripts" / "failure_injector.py"
DEFAULT_LOAD_GENERATOR = ROOT / "scripts" / "load_generator.py"
RESULTS_DIR = ROOT / "results" / "scenarios"


def run_command(command, log_path, cwd=ROOT):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return proc.returncode, time.time() - started


def injector_command(*args):
    return [sys.executable, str(INJECTOR), *map(str, args)]


def run_scenario(name, method, load_generator, csv_path, results_dir,
                 partition_pair=None, crash_args=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = results_dir / f"{method}_{name}_{timestamp}.log"

    if name == "partition":
        a, b = partition_pair
        rc, _ = run_command(
            injector_command("partition-on", a, b),
            results_dir / f"{method}_{name}_injector_{timestamp}.log"
        )
        if rc != 0:
            return {"method": method, "scenario": name, "return_code": rc,
                    "duration_seconds": 0, "log_file": str(log_path),
                    "started_at_utc": timestamp}
    elif name == "crash":
        cmd = injector_command("crash", *crash_args)
        rc, _ = run_command(cmd, results_dir / f"{method}_{name}_injector_{timestamp}.log")
        if rc != 0:
            return {"method": method, "scenario": name, "return_code": rc,
                    "duration_seconds": 0, "log_file": str(log_path),
                    "started_at_utc": timestamp}

    command = [
        sys.executable, str(load_generator),
        "--csv", str(csv_path),
        "--send",
    ]
    rc, duration = run_command(command, log_path)

    if name == "partition":
        run_command(injector_command("partition-off"),
                    results_dir / f"{method}_{name}_restore_{timestamp}.log")

    return {
        "method": method,
        "scenario": name,
        "return_code": rc,
        "duration_seconds": round(duration, 3),
        "log_file": str(log_path),
        "started_at_utc": timestamp,
    }


def main():
    parser = argparse.ArgumentParser(description="Run normal, crash, and partition scenarios.")
    parser.add_argument("--method", required=True, choices=["static", "dynamic"],
                        help="Method label used in output filenames and summary.")
    parser.add_argument("--csv", required=True, type=Path, help="ACN workload CSV.")
    parser.add_argument("--load-generator", type=Path, default=DEFAULT_LOAD_GENERATOR)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--partition-cities", nargs=2, choices=["city1", "city2", "city3"],
                        default=["city1", "city2"], metavar=("CITY_A", "CITY_B"))
    parser.add_argument("--pid-file", type=Path,
                        help="PID file for the CockroachDB node used in crash scenario.")
    parser.add_argument("--store", type=Path, help="Exact CockroachDB store directory.")
    parser.add_argument("--start-command",
                        help="Quoted CockroachDB restart command. Required to restart the node.")
    parser.add_argument("--cwd", type=Path, help="Working directory for CockroachDB start command.")
    parser.add_argument("--wipe-store", action="store_true",
                        help="Delete the CockroachDB store after stopping it (destructive).")
    parser.add_argument("--confirm-wipe", action="store_true",
                        help="Required along with --wipe-store.")
    parser.add_argument("--health-url", help="Optional health URL polled after CockroachDB restart.")
    parser.add_argument("--stop-timeout", type=float, default=10)
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    load_generator = args.load_generator.resolve()
    results_dir = args.results_dir.resolve()
    if not csv_path.is_file():
        parser.error(f"CSV file not found: {csv_path}")
    if not load_generator.is_file():
        parser.error(f"Load generator not found: {load_generator}")
    if args.partition_cities[0] == args.partition_cities[1]:
        parser.error("Partition cities must be different.")
    if args.wipe_store and (not args.store or not args.confirm_wipe):
        parser.error("--wipe-store requires --store and --confirm-wipe.")
    if args.pid_file and not args.start_command:
        parser.error("--pid-file requires --start-command for the crash scenario.")
    if args.start_command and not args.pid_file:
        parser.error("--start-command requires --pid-file.")

    results_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    # Ensure no stale partition config is left from a previous interrupted run.
    run_command(injector_command("partition-off"),
                results_dir / "partition_reset_before_run.log")

    rows.append(run_scenario("normal", args.method, load_generator, csv_path, results_dir))

    if args.pid_file and args.start_command:
        crash_args = [
            "--pid-file", args.pid_file,
            "--start-command", args.start_command,
            "--stop-timeout", args.stop_timeout,
        ]
        if args.store:
            crash_args += ["--store", args.store]
        if args.wipe_store:
            crash_args += ["--wipe-store", "--confirm-wipe"]
        if args.cwd:
            crash_args += ["--cwd", args.cwd]
        if args.health_url:
            crash_args += ["--health-url", args.health_url]
        rows.append(run_scenario("crash", args.method, load_generator, csv_path,
                                 results_dir, crash_args=crash_args))
    else:
        print("Skipping crash scenario: supply --pid-file and --start-command.")

    rows.append(run_scenario("partition", args.method, load_generator, csv_path,
                             results_dir, partition_pair=args.partition_cities))
    run_command(injector_command("partition-off"),
                results_dir / "partition_reset_after_run.log")

    summary = results_dir / f"{args.method}_scenario_summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "method", "scenario", "return_code", "duration_seconds",
            "log_file", "started_at_utc"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print("\nScenario summary")
    print("----------------")
    for row in rows:
        print(f"{row['scenario']:10} return_code={row['return_code']} "
              f"duration={row['duration_seconds']}s")
    print(f"\nSummary CSV: {summary}")
    print("Per-request outcome CSVs are not produced by the current load_generator.py.")


if __name__ == "__main__":
    main()
