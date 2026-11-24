#!/usr/bin/env python3
"""
Failure injector for the EV reservation project.

Supported actions:
  partition-on  - write blocked directed city links to config/partitions.json
  partition-off - clear blocked links
  crash         - stop a CockroachDB process using a PID file, optionally wipe
                  its store, then restart it using a supplied start command.

IMPORTANT:
- The current FastAPI server does not read partitions.json. Partition actions
  therefore record the simulated partition but do not block traffic until the
  server's inter-city forwarding code is taught to consult this file.
- Crash testing is destructive if --wipe-store is supplied. Back up data first.
- The crash action requires an explicit PID file and restart command. It never
  guesses a process or store path.
"""

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARTITION_FILE = PROJECT_ROOT / "config" / "partitions.json"
VALID_CITIES = {"city1", "city2", "city3"}


def write_partition_file(path: Path, blocked_links):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"blocked_links": blocked_links}
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
    print(f"Partition configuration written to: {path}")
    print(json.dumps(payload, indent=2))


def partition_on(args):
    if args.city_a == args.city_b:
        raise ValueError("Choose two different cities.")
    links = [[args.city_a, args.city_b]]
    if not args.one_way:
        links.append([args.city_b, args.city_a])
    write_partition_file(args.file, links)


def partition_off(args):
    write_partition_file(args.file, [])


def read_pid(pid_file: Path) -> int:
    if not pid_file.is_file():
        raise FileNotFoundError(f"PID file does not exist: {pid_file}")
    raw = pid_file.read_text(encoding="utf-8").strip()
    try:
        pid = int(raw)
    except ValueError as exc:
        raise ValueError(f"PID file must contain one numeric PID: {pid_file}") from exc
    if pid <= 1:
        raise ValueError(f"Refusing unsafe PID: {pid}")
    return pid


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_process(pid: int, wait_seconds: float):
    if not process_exists(pid):
        print(f"Process {pid} is already stopped.")
        return
    print(f"Sending SIGTERM to PID {pid}...")
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not process_exists(pid):
            print(f"Process {pid} stopped.")
            return
        time.sleep(0.25)
    print(f"Process {pid} did not stop after {wait_seconds}s; sending SIGKILL.")
    os.kill(pid, signal.SIGKILL)
    time.sleep(0.5)
    if process_exists(pid):
        raise RuntimeError(f"Could not stop process {pid}.")


def crash(args):
    pid_file = args.pid_file.resolve()
    store = args.store.resolve() if args.store else None
    pid = read_pid(pid_file)

    if store is not None and store == Path("/") or (store is not None and len(store.parts) < 3):
        raise ValueError(f"Refusing unsafe store path: {store}")

    print(f"Stopping CockroachDB process from PID file: {pid_file}")
    stop_process(pid, args.stop_timeout)

    if args.wipe_store:
        if store is None:
            raise ValueError("--wipe-store requires --store.")
        if not store.exists():
            print(f"Store path does not exist; nothing to wipe: {store}")
        else:
            if not args.confirm_wipe:
                raise ValueError("Store deletion requires --confirm-wipe as an additional safeguard.")
            print(f"DELETING CockroachDB store: {store}")
            import shutil
            shutil.rmtree(store)

    if not args.start_command:
        print("Node stopped. No --start-command supplied; leaving it stopped.")
        return

    command = shlex.split(args.start_command)
    print("Restarting CockroachDB with:")
    print("  " + " ".join(command))
    log_path = args.log_file.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            command,
            cwd=str(args.cwd.resolve()) if args.cwd else str(PROJECT_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(proc.pid) + "\n", encoding="utf-8")
    print(f"Restart command launched. New PID: {proc.pid}")
    print(f"PID saved to: {pid_file}")
    print(f"Node log: {log_path}")
    if args.health_url:
        import urllib.request
        deadline = time.time() + args.health_timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(args.health_url, timeout=2) as response:
                    if response.status == 200:
                        print(f"Health check passed: {args.health_url}")
                        return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError(f"Health check did not pass within {args.health_timeout}s: {args.health_url}")


def build_parser():
    parser = argparse.ArgumentParser(description="Inject crash and partition failures.")
    sub = parser.add_subparsers(dest="action", required=True)

    on = sub.add_parser("partition-on", help="Record a partition between two cities.")
    on.add_argument("city_a", choices=sorted(VALID_CITIES))
    on.add_argument("city_b", choices=sorted(VALID_CITIES))
    on.add_argument("--one-way", action="store_true", help="Block only city_a -> city_b.")
    on.add_argument("--file", type=Path, default=DEFAULT_PARTITION_FILE)
    on.set_defaults(func=partition_on)

    off = sub.add_parser("partition-off", help="Clear all partition links.")
    off.add_argument("--file", type=Path, default=DEFAULT_PARTITION_FILE)
    off.set_defaults(func=partition_off)

    stop = sub.add_parser("crash", help="Stop a CockroachDB process, optionally wipe its store, and restart it.")
    stop.add_argument("--pid-file", type=Path, required=True, help="File containing the CockroachDB PID.")
    stop.add_argument("--store", type=Path, help="Exact CockroachDB --store directory.")
    stop.add_argument("--wipe-store", action="store_true", help="Delete the exact store directory after stopping.")
    stop.add_argument("--confirm-wipe", action="store_true", help="Required safety confirmation for store deletion.")
    stop.add_argument("--start-command", help='Quoted CockroachDB start command, e.g. "cockroach start --insecure --store=...".')
    stop.add_argument("--cwd", type=Path, help="Working directory for the start command.")
    stop.add_argument("--stop-timeout", type=float, default=10)
    stop.add_argument("--health-url", help="Optional HTTP health URL to poll after restart.")
    stop.add_argument("--health-timeout", type=float, default=60)
    stop.add_argument("--log-file", type=Path, default=PROJECT_ROOT / "results" / "scenarios" / "cockroach-restart.log")
    stop.set_defaults(func=crash)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
