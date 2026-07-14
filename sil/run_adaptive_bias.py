"""Phase 3, strategy 1: adaptive sensor-bias compensation — evaluation.

Runs the identical scenario as run_thermostat_comparison.py (weather, solar,
schedules, Schnellaufheizung supply boost) with BiasCompensatingThermostat
devices, and scores against the two existing baselines:

    ideal PI       (cmp_ideal.csv)      - hardware-free upper bound
    stock eTRV     (cmp_realistic.csv)  - the device pathology baseline
    adaptive eTRV  (this run)           - night-anchor bias compensation

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work/sil && /opt/silenv/bin/python3 run_adaptive_bias.py"
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import kpi
from run_thermostat_comparison import (CONTROL_DT, DURATION, N_APT,
                                       run, supply_controller)
from scenario_common import C2K, DAY, SCHEDULES, day_night_setpoint
from controllers import ScriptedValve
from strategies import BiasCompensatingThermostat
from thermostat import SampledPI

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def build_adaptive():
    controllers = {"TSupSet": supply_controller()}
    for i in range(1, N_APT + 1):
        sched = SCHEDULES.get(i)
        if sched is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        else:
            controllers[f"yVal[{i}]"] = BiasCompensatingThermostat(
                temp_output=f"TRoom[{i}]",
                q_rad_output=f"QRad[{i}]",
                dp_output=f"dpVal[{i}]",
                algorithm=SampledPI(day_night_setpoint(*sched)),
                seed=i)
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


def per_day_discomfort(df, day):
    win = df[(df["time"] >= day * DAY) & (df["time"] < (day + 1) * DAY)]
    d, _ = occupied_kpis(win)
    return d


def main():
    controllers = build_adaptive()
    df_adapt = run("adaptive-bias", controllers,
                   "eTRV + adaptive bias compensation")

    df_ideal = pd.read_csv(RESULTS / "cmp_ideal.csv")
    df_stock = pd.read_csv(RESULTS / "cmp_realistic.csv")

    print(f"\n{'KPI (days 2-7)':42s} {'ideal PI':>10s} {'stock eTRV':>11s} "
          f"{'adaptive':>10s}")
    rows = []
    for label, fn in [("discomfort (K*h)", lambda d: occupied_kpis(d)[0]),
                      ("overheating (K*h)", lambda d: occupied_kpis(d)[1]),
                      ("boiler energy (kWh)", kpi.boiler_energy_kwh)]:
        vals = [fn(df_ideal), fn(df_stock), fn(df_adapt)]
        rows.append((label, vals))
        print(f"{label:42s} {vals[0]:10.1f} {vals[1]:11.1f} {vals[2]:10.1f}")

    devices = [c for c in controllers.values()
               if isinstance(c, BiasCompensatingThermostat)]
    travel, moves = kpi.battery_kpis(devices)
    print(f"{'valve travel (strokes) / moves':42s} {'—':>10s} "
          f"{'305.8/3108':>11s} {travel:6.1f}/{moves}")
    for d in devices:
        i = d.temp_output
        ks = ", ".join(f"{k:.2f}" for _, k in d.k_log)
        print(f"  {i}: k_hat trajectory [{ks}]")

    # ---- figure: room 1 stock vs adaptive + k_hat convergence ----
    sched1 = day_night_setpoint(*SCHEDULES[1])
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 10))

    win_s = (df_stock["time"] >= 5 * DAY) & (df_stock["time"] <= 7 * DAY)
    win_a = (df_adapt["time"] >= 5 * DAY) & (df_adapt["time"] <= 7 * DAY)
    ax1.plot(df_stock["time"][win_s] / DAY, df_stock["TRoom[1]"][win_s] - C2K,
             label="stock eTRV", color="#B8432F", lw=1.0)
    ax1.plot(df_adapt["time"][win_a] / DAY, df_adapt["TRoom[1]"][win_a] - C2K,
             label="adaptive eTRV", color="#2E5E8C", lw=1.0)
    ax1.plot(df_adapt["time"][win_a] / DAY,
             [sched1(t) - C2K for t in df_adapt["time"][win_a]],
             ls="--", lw=0.8, color="gray", label="setpoint")
    ax1.set_ylabel("apartment 1 / °C")
    ax1.set_title("Adaptive sensor-bias compensation: true room temperature, days 5-7")
    ax1.legend(fontsize=8)

    for d in devices:
        ts = [t / DAY for t, _ in d.k_log]
        ks = [k for _, k in d.k_log]
        ax2.step([0] + ts, [0] + ks, where="post", label=d.temp_output)
    ax2.set_ylabel("learned bias gain k̂ / K")
    ax2.set_xlabel("time / days")
    ax2.legend(fontsize=7, ncol=3)
    ax2.set_title("Night-anchor learning: one update per closure, converged in ~2 nights")

    days = list(range(1, 7))
    ax3.plot(days, [per_day_discomfort(df_stock, d) for d in days],
             "o-", color="#B8432F", label="stock eTRV")
    ax3.plot(days, [per_day_discomfort(df_adapt, d) for d in days],
             "o-", color="#2E5E8C", label="adaptive eTRV")
    ax3.plot(days, [per_day_discomfort(df_ideal, d) for d in days],
             "o--", color="gray", label="ideal PI")
    ax3.set_ylabel("discomfort / K·h per day")
    ax3.set_xlabel("day")
    ax3.legend(fontsize=8)
    ax3.set_title("Comfort converges toward the ideal-PI bound as k̂ is learned")

    fig.tight_layout()
    fig.savefig(RESULTS / "adaptive_bias.png", dpi=150)
    print("\nwrote results/adaptive_bias.png")


if __name__ == "__main__":
    main()
