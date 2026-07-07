"""
MeshNet-AI — config.py
======================
Centralised disaster scenario configuration.

Each scenario entry carries:
  • range_km              : operational coverage radius in kilometres
  • battery_threshold_warn: UI warning level (% below which node shows orange)
  • max_hops              : maximum relay hops for a single SOS packet
  • priority_device_types : device tiers preferred by the router for this scenario
  • description           : human-readable blurb shown in the GUI

These values are consumed by:
  • core_router.MeshNetRouter  — selects the active range and hop limit
  • ui.SCENARIOS               — populates the scenario selector panel
  • dashboard_offline          — header display
"""

from __future__ import annotations

from typing import TypedDict


class ScenarioConfig(TypedDict):
    range_km              : int
    battery_threshold_warn: int
    max_hops              : int
    priority_device_types : list[str]
    description           : str


# ── Per-scenario parameters ───────────────────────────────────────────────────

SCENARIOS: dict[str, ScenarioConfig] = {
    "Flood": {
        "range_km"              : 50,
        "battery_threshold_warn": 30,
        "max_hops"              : 8,
        "priority_device_types" : ["gateway", "relay"],
        "description"           : (
            "Elevated terrain nodes preferred. "
            "Max 8 hops. Battery warn at 30 %. "
            "Range: 50 km."
        ),
    },
    "Earthquake": {
        "range_km"              : 70,
        "battery_threshold_warn": 25,
        "max_hops"              : 10,
        "priority_device_types" : ["gateway", "relay", "smartphone"],
        "description"           : (
            "Wide-area coverage. Max 10 hops. "
            "Battery warn at 25 %. "
            "Range: 70 km."
        ),
    },
    "War Zone": {
        "range_km"              : 30,
        "battery_threshold_warn": 40,
        "max_hops"              : 5,
        "priority_device_types" : ["gateway"],
        "description"           : (
            "Minimal RF footprint. Max 5 hops. "
            "Battery warn at 40 %. "
            "Encryption enforced. Range: 30 km."
        ),
    },
}

# ── Legacy scalar attributes (backward compat with core_router.py) ────────────
# core_router.py reads:  config.Flood / config.War_Zone / config.Earthquake

Flood      : int = SCENARIOS["Flood"]["range_km"]
War_Zone   : int = SCENARIOS["War Zone"]["range_km"]
Earthquake : int = SCENARIOS["Earthquake"]["range_km"]

# ── Convenience helpers ───────────────────────────────────────────────────────

def get_scenario(name: str) -> ScenarioConfig:
    """
    Return the ScenarioConfig for *name*.
    Raises KeyError with a clear message if the name is not registered.
    """
    if name not in SCENARIOS:
        raise KeyError(
            f"Unknown scenario '{name}'. "
            f"Valid options: {list(SCENARIOS.keys())}"
        )
    return SCENARIOS[name]


def scenario_names() -> list[str]:
    """Return the list of registered scenario names in definition order."""
    return list(SCENARIOS.keys())


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("MeshNet-AI — Scenario Configuration")
    print("=" * 50)
    for name, cfg in SCENARIOS.items():
        print(f"\n  [{name}]")
        print(f"    Range        : {cfg['range_km']} km")
        print(f"    Max hops     : {cfg['max_hops']}")
        print(f"    Battery warn : {cfg['battery_threshold_warn']} %")
        print(f"    Priority devs: {', '.join(cfg['priority_device_types'])}")
        print(f"    Description  : {cfg['description']}")
