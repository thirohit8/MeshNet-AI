"""
MeshNet-AI — dashboard_offline.py
===================================
Real-time offline terminal dashboard.

Cycles through all disaster scenarios in an auto-refreshing terminal loop,
displaying:
  • Active peer table (node ID, device, battery, routing score, priority)
  • Routing path  (hop chain with Weather-HQ annotation)
  • Scenario configuration (range, max hops, battery warning threshold)
  • Network health summary

Controls
--------
    Ctrl-C   — graceful exit
    --once   — render one pass for each scenario and exit (CI/testing mode)

Usage
-----
    python3 dashboard_offline.py
    python3 dashboard_offline.py --scenario Flood
    python3 dashboard_offline.py --once
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import config
from core_router import MeshNetRouter
from nodes_mock import simulated_network


# ── ANSI colour helpers (degrade gracefully on Windows / dumb terminals) ──────

_ANSI = os.environ.get("TERM", "dumb") not in ("dumb", "")

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ANSI else text

def _bold(t: str)    -> str: return _c("1",       t)
def _green(t: str)   -> str: return _c("32",      t)
def _yellow(t: str)  -> str: return _c("33",      t)
def _red(t: str)     -> str: return _c("31",      t)
def _cyan(t: str)    -> str: return _c("96",      t)
def _amber(t: str)   -> str: return _c("38;5;214", t)
def _dim(t: str)     -> str: return _c("2",       t)


# ── Dashboard renderer ────────────────────────────────────────────────────────

def render_dashboard(scenario: str) -> None:
    """
    Clear the terminal and render one full dashboard frame for *scenario*.
    """
    os.system("clear" if os.name != "nt" else "cls")

    router = MeshNetRouter(simulated_network, scenario)
    routes = router.calculate_safe_routes()
    result = router.compute_full_result()
    cfg    = config.get_scenario(scenario)

    now     = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    total   = len(simulated_network)
    stable  = len(routes)
    dropped = total - stable

    # ── Header ────────────────────────────────────────────────────────────────
    print(_bold("=" * 70))
    print(_bold(_cyan(
        "         MeshNet-AI  |  EMERGENCY COMMAND CENTER  (OFFLINE)"
    )))
    print(_bold("=" * 70))
    print(
        f"  {_bold('Scenario')} : {_amber(scenario):<20}  "
        f"{_bold('Time')} : {_dim(now)}"
    )
    print(
        f"  {_bold('Range')}    : {cfg['range_km']} km       "
        f"  {_bold('Max hops')}    : {cfg['max_hops']}   "
        f"  {_bold('Batt warn')} : {cfg['battery_threshold_warn']} %"
    )
    print(
        f"  {_bold('Topology')} : {total} nodes total  "
        f"  {_green(str(stable) + ' stable')}  "
        f"  {_red(str(dropped) + ' filtered')}"
    )
    print(_dim("-" * 70))

    # ── Routing path ──────────────────────────────────────────────────────────
    if result.optimal_path:
        hq_note = (
            _amber(f"  ← Weather-HQ anchor: {result.hq_anchor}")
            if result.hq_anchor else ""
        )
        path_str = " → ".join(result.optimal_path)
        print(
            f"\n  {_bold('Optimal Path')}  "
            f"(quality {_green(f'{result.path_quality:.2%}')}){hq_note}"
        )
        print(f"    {_cyan(path_str)}")
    else:
        print(f"\n  {_red('No stable routing path available.')}")

    # ── Peer table ────────────────────────────────────────────────────────────
    print()
    print(_dim("-" * 70))
    hdr = (
        f"  {'NODE ID':<14} {'DEVICE':<12} {'BATTERY':>8}  "
        f"{'SCORE':>7}  {'PRIORITY':<10}  RANGE"
    )
    print(_bold(hdr))
    print(_dim("-" * 70))

    for route in routes:
        batt  = route["battery"]
        score = route["routing_score"]
        pri   = route["priority_status"]

        # Colour-code battery level
        batt_str = f"{batt:3d}%"
        if batt < cfg["battery_threshold_warn"]:
            batt_str = _yellow(batt_str)
        elif batt >= 70:
            batt_str = _green(batt_str)

        # Star + colour for priority
        if pri == "HIGH":
            pri_str = _amber("★ HIGH    ")
        elif pri == "MEDIUM":
            pri_str = _cyan("  MEDIUM  ")
        else:
            pri_str = _dim("  NORMAL  ")

        score_str = _green(f"{score:.4f}") if score >= 0.6 else f"{score:.4f}"

        print(
            f"  {route['node_id']:<14} {route['device']:<12} {batt_str:>8}  "
            f"{score_str:>7}  {pri_str}  {route['allowed_range_km']} km"
        )

    print(_dim("=" * 70))
    print(
        _dim(
            f"  Path quality: {result.path_quality:.2%}   "
            f"Hops: {len(result.optimal_path)}   "
            f"HQ anchor: {result.hq_anchor or 'none'}   "
            "Press Ctrl-C to exit."
        )
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dashboard_offline",
        description="MeshNet-AI — Real-time Offline Emergency Dashboard",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        choices=config.scenario_names(),
        help="Pin to a single scenario (default: cycle through all)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=4.0,
        help="Seconds between screen refreshes (default: 4)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Render one pass per scenario and exit (for CI / testing)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args     = _parse_args()
    interval = args.interval

    scenarios = (
        [args.scenario]
        if args.scenario
        else config.scenario_names()
    )

    try:
        if args.once:
            for s in scenarios:
                render_dashboard(s)
                print()
            sys.exit(0)

        # Continuous auto-refresh loop
        while True:
            for s in scenarios:
                render_dashboard(s)
                time.sleep(interval)

    except KeyboardInterrupt:
        print(
            "\n\n  [INFO] Dashboard stopped.  "
            "Secure connection closed.  MeshNet-AI offline.  \n"
        )
        sys.exit(0)
