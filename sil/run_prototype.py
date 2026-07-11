"""Prototype SIL runs against build/PrototypeTwoRooms.fmu.

Scenario A: winter week with two independent PI thermostats and
            night-setback schedules (closed-loop SIL demonstration).
Scenario B: hydraulic coupling — valve 1 closes, flow shifts to radiator 2
            (the physical interaction distributed control must handle).

Run inside the container:
  docker run --rm -v ${PWD}:/work -w /work buildingsimulator:dev python3 sil/run_prototype.py
"""

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from harness import run_simulation
from controllers import PIThermostat, ScriptedValve

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "PrototypeTwoRooms.fmu")
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

OUTPUTS = ["TRoom1", "TRoom2", "TSup", "TRet", "mFlow1", "mFlow2", "QBoi"]

C2K = 273.15
DAY = 86400.0


def heating_curve(t_out_k: float) -> float:
    """Outdoor-reset supply temperature setpoint (65 degC @ -10, 35 degC @ +15)."""
    t_out = t_out_k - C2K
    t_sup = 35.0 + (65.0 - 35.0) * (15.0 - t_out) / 25.0
    return min(max(t_sup, 35.0), 65.0) + C2K


def winter_weather(t: float) -> float:
    """Sinusoidal outdoor temperature: -2 degC mean, +/-4 K daily swing, min at 04:00."""
    return C2K - 2.0 + 4.0 * math.sin(2.0 * math.pi * (t - 10.0 * 3600.0) / DAY)


def day_night_setpoint(day_sp, night_sp, day_start_h, day_end_h):
    def sp(t):
        hour = (t % DAY) / 3600.0
        return (day_sp if day_start_h <= hour < day_end_h else night_sp) + C2K
    return sp


def scenario_a():
    print("Scenario A: winter week, PI thermostats with night setback ...")

    def exogenous(t):
        t_out = winter_weather(t)
        return {"TOut": t_out, "TSupSet": heating_curve(t_out)}

    controllers = {
        "yVal1": PIThermostat("TRoom1", day_night_setpoint(21.0, 17.0, 6, 22)),
        "yVal2": PIThermostat("TRoom2", day_night_setpoint(21.0, 16.0, 8, 20)),
    }
    records = run_simulation(FMU, controllers, exogenous, duration=7 * DAY,
                             control_dt=60.0, output_names=OUTPUTS, record_dt=300.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / "scenario_a_winter_week.csv", index=False)

    days = df["time"] / DAY
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    ax = axes[0]
    ax.plot(days, df["TRoom1"] - C2K, label="room 1")
    ax.plot(days, df["TRoom2"] - C2K, label="room 2")
    ax.plot(days, [day_night_setpoint(21, 17, 6, 22)(t) - C2K for t in df["time"]],
            ls="--", lw=0.8, label="setpoint 1")
    ax.plot(days, [day_night_setpoint(21, 16, 8, 20)(t) - C2K for t in df["time"]],
            ls="--", lw=0.8, label="setpoint 2")
    ax.plot(days, df["TOut"] - C2K, color="gray", lw=0.8, label="outdoor")
    ax.set_ylabel("temperature / °C")
    ax.legend(loc="center right", fontsize=8)
    ax.set_title("Winter week — PI thermostats (SIL), night setback")

    ax = axes[1]
    ax.plot(days, df["yVal1"], label="valve 1")
    ax.plot(days, df["yVal2"], label="valve 2")
    ax.set_ylabel("valve position / –")
    ax.legend(loc="center right", fontsize=8)

    ax = axes[2]
    ax.plot(days, df["TSup"] - C2K, label="supply")
    ax.plot(days, df["TRet"] - C2K, label="return")
    ax.set_ylabel("water temperature / °C")
    ax.set_xlabel("time / days")
    ax.legend(loc="center right", fontsize=8)

    fig.tight_layout()
    fig.savefig(RESULTS / "scenario_a_winter_week.png", dpi=150)
    print(f"  mean room1 (day 2-7): "
          f"{(df[df['time'] > DAY]['TRoom1'] - C2K).mean():.2f} degC")
    print(f"  boiler energy: {df['QBoi'].mean() * 7 * 24 / 1000:.1f} kWh/week")


def scenario_b():
    print("Scenario B: hydraulic coupling, valve 1 closes at t = 6 h ...")

    def exogenous(t):
        return {"TOut": C2K - 5.0, "TSupSet": C2K + 60.0}

    controllers = {
        "yVal1": ScriptedValve([(0.0, 1.0), (6 * 3600.0, 0.0)]),
        "yVal2": ScriptedValve([(0.0, 1.0)]),
    }
    records = run_simulation(FMU, controllers, exogenous, duration=12 * 3600.0,
                             control_dt=60.0, output_names=OUTPUTS, record_dt=60.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / "scenario_b_coupling.csv", index=False)

    hours = df["time"] / 3600.0
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

    ax1.plot(hours, df["mFlow1"] * 1000, label="radiator 1")
    ax1.plot(hours, df["mFlow2"] * 1000, label="radiator 2")
    ax1.axvline(6, color="gray", ls=":", lw=1)
    ax1.annotate("valve 1 closes", xy=(6, ax1.get_ylim()[1]), fontsize=8,
                 xytext=(6.2, df["mFlow1"].max() * 1000 * 0.9))
    ax1.set_ylabel("mass flow / g/s")
    ax1.legend()
    ax1.set_title("Hydraulic coupling: closing valve 1 shifts flow to radiator 2")

    ax2.plot(hours, df["TRoom1"] - C2K, label="room 1")
    ax2.plot(hours, df["TRoom2"] - C2K, label="room 2")
    ax2.axvline(6, color="gray", ls=":", lw=1)
    ax2.set_ylabel("room temperature / °C")
    ax2.set_xlabel("time / h")
    ax2.legend()

    fig.tight_layout()
    fig.savefig(RESULTS / "scenario_b_coupling.png", dpi=150)

    before = df[(df["time"] > 5 * 3600) & (df["time"] < 6 * 3600)]["mFlow2"].mean()
    after = df[df["time"] > 11 * 3600]["mFlow2"].mean()
    print(f"  radiator 2 flow before/after: {before*1000:.2f} -> {after*1000:.2f} g/s "
          f"({(after/before - 1)*100:+.1f} %)")


if __name__ == "__main__":
    scenario_b()
    scenario_a()
    print("done — plots and CSVs in results/")
