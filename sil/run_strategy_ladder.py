"""Phase 3: evaluate strategy-ladder rungs 2 and 3 on the baseline scenario.

Runs (identical scenario as all baselines — weather, solar, schedules,
Schnellaufheizung supply boost):

    battery-aware   BiasComp + comfort-scaled deadband + reopen dwell
    optimal-start   BiasComp + battery policies + learned per-room lead time

and prints the full ladder KPI table against ideal PI (cmp_ideal.csv),
stock eTRV (cmp_realistic.csv) and adaptive bias (cmp_adaptive-bias.csv).

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work/sil && /opt/silenv/bin/python3 run_strategy_ladder.py"
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import kpi
from run_thermostat_comparison import (N_APT, run, supply_controller)
from scenario_common import C2K, DAY, SCHEDULES, day_night_setpoint
from controllers import ScriptedValve
from strategies import BatteryAwareThermostat, OptimalStartThermostat
from thermostat import SampledPI

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def device_kwargs(i):
    return dict(temp_output=f"TRoom[{i}]", q_rad_output=f"QRad[{i}]",
                dp_output=f"dpVal[{i}]", seed=i)


def build(strategy):
    controllers = {"TSupSet": supply_controller()}
    for i in range(1, N_APT + 1):
        sched = SCHEDULES.get(i)
        if sched is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        elif strategy == "battery":
            controllers[f"yVal[{i}]"] = BatteryAwareThermostat(
                algorithm=SampledPI(day_night_setpoint(*sched)),
                **device_kwargs(i))
        elif strategy == "optimal":
            controllers[f"yVal[{i}]"] = OptimalStartThermostat(
                schedule=sched,
                algorithm_factory=lambda sp: SampledPI(sp),
                **device_kwargs(i))
    return controllers


def occupied_kpis(df):
    disc = over = 0.0
    for i, sched in SCHEDULES.items():
        if sched is None:
            continue
        sp = day_night_setpoint(*sched)
        disc += kpi.discomfort_kh(df, f"TRoom[{i}]", sp)
        over += kpi.overheat_kh(df, f"TRoom[{i}]", sp)
    return disc, over


def main():
    ctrl_b = build("battery")
    df_b = run("battery-aware", ctrl_b, "eTRV + bias comp + battery policies")
    ctrl_o = build("optimal")
    df_o = run("optimal-start", ctrl_o,
               "eTRV + bias comp + battery + optimal start")

    frames = {
        "ideal PI": pd.read_csv(RESULTS / "cmp_ideal.csv"),
        "stock eTRV": pd.read_csv(RESULTS / "cmp_realistic.csv"),
        "adaptive": pd.read_csv(RESULTS / "cmp_adaptive-bias.csv"),
        "battery": df_b,
        "opt-start": df_o,
    }
    travels = {"battery": ctrl_b, "opt-start": ctrl_o}

    cols = list(frames)
    print(f"\n{'KPI (days 2-7)':34s} " + " ".join(f"{c:>10s}" for c in cols))
    for label, fn in [("discomfort (K*h)", lambda d: occupied_kpis(d)[0]),
                      ("overheating (K*h)", lambda d: occupied_kpis(d)[1]),
                      ("boiler energy (kWh)", kpi.boiler_energy_kwh)]:
        vals = [fn(frames[c]) for c in cols]
        print(f"{label:34s} " + " ".join(f"{v:10.1f}" for v in vals))
    for name, ctrl in travels.items():
        devs = [c for c in ctrl.values() if hasattr(c, "travel")]
        travel, moves = kpi.battery_kpis(devs)
        print(f"{name:34s} travel {travel:6.1f} strokes | {moves} moves")
    for name, ctrl in travels.items():
        for c in ctrl.values():
            if hasattr(c, "lead_log") and c.lead_log:
                leads = ", ".join(f"{s/60:.0f}m" for _, s in c.lead_log)
                print(f"  {c.temp_output} lead trajectory: [{leads}]")

    # ---- figure: morning arrival (day 6) + travel bars ----
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8))
    sched1 = SCHEDULES[1]
    day = 6
    for name, color in [("adaptive", "#B8432F"), ("opt-start", "#2E5E8C"),
                        ("ideal PI", "gray")]:
        df = frames[name]
        w = ((df["time"] >= (day + sched1[2] / 24 - 0.2) * DAY)
             & (df["time"] <= (day + sched1[2] / 24 + 0.25) * DAY))
        ax1.plot(df["time"][w] / DAY % 1 * 24, df["TRoom[1]"][w] - C2K,
                 label=name, color=color,
                 ls="--" if name == "ideal PI" else "-")
    ax1.axvline(sched1[2], color="gray", ls=":", lw=0.8)
    ax1.axhline(sched1[0], color="gray", ls="--", lw=0.8)
    ax1.set_xlabel(f"hour of day {day}")
    ax1.set_ylabel("apartment 1 / °C")
    ax1.set_title("Optimal start: the room arrives AT day start instead of ~1.5 h after")
    ax1.legend(fontsize=8)

    names = ["stock eTRV", "adaptive", "battery", "opt-start"]
    travel_vals = [305.8, 274.3]
    for name in ["battery", "opt-start"]:
        devs = [c for c in travels[name].values() if hasattr(c, "travel")]
        travel_vals.append(kpi.battery_kpis(devs)[0])
    ax2.bar(names, travel_vals, color=["#B8432F", "#C97B4A", "#2E5E8C", "#4C7FB0"])
    ax2.set_ylabel("valve travel / strokes per week")
    ax2.set_title("Battery cost down the ladder")

    fig.tight_layout()
    fig.savefig(RESULTS / "strategy_ladder.png", dpi=150)
    print("\nwrote results/strategy_ladder.png")


if __name__ == "__main__":
    main()
