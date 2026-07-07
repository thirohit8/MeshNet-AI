"""
MeshNet-AI — launcher.py
=========================
Master CLI control panel.

Provides an interactive terminal menu that gives direct access to every
subsystem of MeshNet-AI without launching the full Kivy GUI:

  1. Emergency Dashboard    — real-time cycling terminal dashboard
  2. Core Router Self-Test  — scenario routing for all 3 disaster types
  3. Broadcast SOS          — hop-by-hop packet propagation simulation
  4. View Encrypted Logs    — decrypt and display handshake log entries
  5. Node Topology Audit    — list and score all mock network nodes
  6. Exit

Usage
-----
    python3 launcher.py          # interactive menu
    python3 launcher.py --auto 3 # auto-select option 3 (for scripting)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# ── Kivy headless environment guard ──────────────────────────────────────────
# Must be set before any sub-module that imports Kivy is loaded.
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")
os.environ.setdefault("DISPLAY", ":0")


# ── ANSI helpers ──────────────────────────────────────────────────────────────

_ANSI = os.environ.get("TERM", "dumb") not in ("dumb", "")

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ANSI else text

def _bold(t: str)  -> str: return _c("1",  t)
def _cyan(t: str)  -> str: return _c("96", t)
def _red(t: str)   -> str: return _c("31", t)
def _green(t: str) -> str: return _c("32", t)
def _amber(t: str) -> str: return _c("38;5;214", t)
def _dim(t: str)   -> str: return _c("2",  t)


# ── Menu helpers ──────────────────────────────────────────────────────────────

_MENU_WIDTH = 64

def _header() -> None:
    os.system("clear" if os.name != "nt" else "cls")
    print(_bold("=" * _MENU_WIDTH))
    print(_bold(_cyan(
        "   🛡  MeshNet-AI  |  Offline Emergency Mesh  |  v1.0   🛡"
    )))
    print(_bold("=" * _MENU_WIDTH))
    print(_dim("   Platform: Offline  |  Internet required: NONE"))
    print(_bold("-" * _MENU_WIDTH))


def _menu() -> str:
    _header()
    options = [
        ("1", "Emergency Dashboard",    "Real-time cycling command-center terminal"),
        ("2", "Core Router Self-Test",  "Run routing engine across all 3 scenarios"),
        ("3", "Broadcast SOS Packet",   "Simulate hop-by-hop radio propagation"),
        ("4", "View Encrypted Logs",    "Decrypt and display handshake log entries"),
        ("5", "Node Topology Audit",    "List and score all mock network nodes"),
        ("6", "Exit",                   "Close the control panel"),
    ]
    for num, title, desc in options:
        num_str  = _amber(f" [{num}]")
        title_str= _bold(f"  {title:<28}")
        desc_str = _dim(desc)
        print(f"{num_str}{title_str}  {desc_str}")
    print(_bold("=" * _MENU_WIDTH))
    return input(_cyan("   Enter your choice (1–6): ")).strip()


# ── Option handlers ───────────────────────────────────────────────────────────

def _opt_dashboard() -> None:
    """Launch the auto-cycling offline dashboard (Ctrl-C to return)."""
    print(_dim("\n  [INFO] Starting Emergency Dashboard — Ctrl-C to return…\n"))
    time.sleep(0.5)
    os.system(f"{sys.executable} dashboard_offline.py")


def _opt_router_test() -> None:
    """Run the core router self-test across all scenarios."""
    print(_dim("\n  [INFO] Running Core Router Self-Test…\n"))
    from config import scenario_names, get_scenario
    from nodes_mock import simulated_network
    from core_router import MeshNetRouter

    for scenario in scenario_names():
        cfg    = get_scenario(scenario)
        router = MeshNetRouter(simulated_network, scenario)
        result = router.compute_full_result()
        routes = router.calculate_safe_routes()

        print(_bold(f"\n  ─── Scenario: {scenario} ───"))
        print(
            f"  Range: {cfg['range_km']} km  |  "
            f"Max hops: {cfg['max_hops']}  |  "
            f"Stable nodes: {len(routes)}"
        )
        print(
            f"  Path hops: {len(result.optimal_path)}  |  "
            f"Quality: {_green(f'{result.path_quality:.2%}')}  |  "
            f"HQ anchor: {_amber(result.hq_anchor) if result.hq_anchor else _dim('none')}"
        )
        print(f"  Hop chain: {_cyan(' → '.join(result.optimal_path))}")
        print()
        for r in routes:
            star = _amber("★") if r["priority_status"] == "HIGH" else " "
            print(
                f"    {star} {r['node_id']:<14} {r['device']:<12} "
                f"batt={r['battery']:3d}%  score={r['routing_score']:.4f}  "
                f"{r['priority_status']}"
            )

    input(_dim("\n  Press Enter to return to main menu…"))


def _opt_broadcast() -> None:
    """Simulate hop-by-hop SOS packet propagation."""
    from config import scenario_names

    print(_bold("\n  Available scenarios:"))
    for i, s in enumerate(scenario_names(), 1):
        print(f"    [{i}] {s}")
    raw = input(_cyan("  Select scenario number (default 1): ")).strip()

    names = scenario_names()
    try:
        idx      = int(raw) - 1
        scenario = names[idx]
    except (ValueError, IndexError):
        scenario = names[0]

    custom_msg = input(
        _dim(f"  Custom SOS message (Enter to auto-generate): ")
    ).strip()

    print(_dim(f"\n  [INFO] Launching broadcast for scenario: {scenario}…\n"))

    # Patch Kivy Clock for headless CLI use
    from emergency_messaging import ConsoleBroadcast, _patch_clock
    _patch_clock()

    harness = ConsoleBroadcast(scenario=scenario)
    harness.run(message=custom_msg)

    input(_dim("  Press Enter to return to main menu…"))


def _opt_view_logs() -> None:
    """Decrypt and display all stored handshake log entries."""
    print(_dim("\n  [INFO] Reading encrypted handshake log…\n"))

    from emergency_messaging import _patch_clock
    _patch_clock()

    from messaging import HandshakeLogger
    harness_logger = HandshakeLogger()
    records = harness_logger.read_all()

    if not records:
        print(_amber("  [INFO] No log entries found.  "
                     "Run a broadcast first to generate records."))
    else:
        print(_bold(f"\n  MeshNet-AI — Encrypted Log  ({len(records)} records)"))
        print(_dim("  " + "-" * 58))
        for i, rec in enumerate(records, 1):
            hops = rec.get("path", [])
            print(
                f"\n  [{i}] {_bold(rec.get('packet_id', 'N/A'))}"
                f"\n       Scenario  : {rec.get('scenario', 'N/A')}"
                f"\n       Origin    : {rec.get('origin_node', 'N/A')}"
                f"\n       Timestamp : {_dim(rec.get('created_at', 'N/A'))}"
                f"\n       Hops ({len(hops):2d}) : {_cyan(' → '.join(hops))}"
                f"\n       Message   : {rec.get('message', '')[:75]}"
            )

    input(_dim("\n  Press Enter to return to main menu…"))


def _opt_topology_audit() -> None:
    """List and score all mock network nodes."""
    from nodes_mock import MOCK_TOPOLOGY
    from routing import RoutingEngine

    engine = RoutingEngine()
    result = engine.compute(list(MOCK_TOPOLOGY))

    print(_bold(f"\n  MeshNet-AI — Node Topology Audit"))
    print(
        _dim(
            f"  Total: {len(MOCK_TOPOLOGY)}  |  "
            f"Stable: {len(result.stable_nodes)}  |  "
            f"Filtered: {result.rejected_count}"
        )
    )
    print(_dim("  " + "-" * 70))
    fmt = "  {:<14} {:<12} {:>5}% {:>7}  {:>5}  {:<10}  {}"
    print(_bold(fmt.format(
        "NODE ID", "DEVICE", "BATT", "SCORE", "HQ", "STATUS", "COORDS"
    )))
    print(_dim("  " + "-" * 70))

    score_map = {n.node_id: n.routing_score for n in result.stable_nodes}
    for n in MOCK_TOPOLOGY:
        score  = score_map.get(n.node_id, None)
        active = n.is_active and n.battery_level > 15

        if not active:
            status_str = _red("FILTERED")
            score_str  = _dim("  ----")
        elif score is not None and score >= 0.6:
            status_str = _green("STABLE")
            score_str  = _green(f"{score:.4f}")
        else:
            status_str = _dim("STABLE")
            score_str  = f"{score:.4f}" if score is not None else "  ----"

        hq_str = _amber("YES") if n.has_weather_hq_signal else _dim(" no")
        coord  = f"({n.lat:.4f}, {n.lon:.4f})"

        print(fmt.format(
            n.node_id, n.device_type,
            int(n.battery_level), score_str,
            hq_str, status_str, coord,
        ))

    print()
    if result.optimal_path:
        print(
            f"  {_bold('Optimal path')} : "
            f"{_cyan(' → '.join(result.optimal_path))}"
        )
        print(
            f"  {_bold('Path quality')} : {_green(f'{result.path_quality:.2%}')}  |  "
            f"HQ anchor : {_amber(result.hq_anchor) if result.hq_anchor else _dim('none')}"
        )

    input(_dim("\n  Press Enter to return to main menu…"))


# ── Main loop ─────────────────────────────────────────────────────────────────

_DISPATCH = {
    "1": _opt_dashboard,
    "2": _opt_router_test,
    "3": _opt_broadcast,
    "4": _opt_view_logs,
    "5": _opt_topology_audit,
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="launcher",
        description="MeshNet-AI — Master CLI Control Panel",
    )
    p.add_argument(
        "--auto",
        metavar="CHOICE",
        default=None,
        help="Automatically select menu option (1–6) without prompting",
    )
    return p.parse_args()


def run() -> None:
    args = _parse_args()

    if args.auto:
        choice = args.auto.strip()
        if choice in _DISPATCH:
            _DISPATCH[choice]()
        elif choice == "6":
            pass
        else:
            print(f"[ERROR] Invalid --auto choice: {choice!r}", file=sys.stderr)
            sys.exit(1)
        return

    while True:
        try:
            choice = _menu()
        except KeyboardInterrupt:
            choice = "6"

        if choice in _DISPATCH:
            try:
                _DISPATCH[choice]()
            except KeyboardInterrupt:
                pass   # Return to menu on Ctrl-C inside a sub-option
        elif choice == "6":
            print(
                _green(
                    "\n  [OK] MeshNet-AI offline.  "
                    "Secure logs preserved.  Goodbye.\n"
                )
            )
            sys.exit(0)
        else:
            input(_red("  [ERROR] Invalid choice.  Press Enter to try again…"))


if __name__ == "__main__":
    run()
