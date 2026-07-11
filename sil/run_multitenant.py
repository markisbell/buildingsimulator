"""Multi-tenant building SIL runs against build/MultiTenantBuilding.fmu.

Scenario A: flow balancing — all valves fully open, constant cold day.
            Shows the floor-dependent flow imbalance caused by riser losses.
Scenario B: winter week — one PI thermostat per apartment, staggered
            schedules, apartment 3 vacant (valve shut). Shows closed-loop
            multi-zone control and heat theft through floor/ceiling.

Run inside the container:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev python3 run_multitenant.py
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fmpy import read_model_description

from harness import run_simulation
from controllers import PIThermostat, ScriptedValve
from scenario_common import (C2K, DAY, SCHEDULES, day_night_setpoint,
                             heating_curve, winter_weather)

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

def apartment_count(fmu_path: str) -> int:
    md = read_model_description(fmu_path)
    return len([v for v in md.modelVariables
                if re.fullmatch(r"TRoom\[\d+\]", v.name)])


N_APT = apartment_count(FMU)
VALVES = [f"yVal[{i}]" for i in range(1, N_APT + 1)]
TROOMS = [f"TRoom[{i}]" for i in range(1, N_APT + 1)]
MFLOWS = [f"mFlow[{i}]" for i in range(1, N_APT + 1)]
OUTPUTS = TROOMS + MFLOWS + ["TSup", "TRet", "QBoi", "PPum"]

print(f"FMU has {N_APT} apartments")


def scenario_a():
    print("Scenario A: flow balancing, all valves open ...")

    def exogenous(t):
        return {"TOut": C2K - 5.0, "TSupSet": C2K + 60.0}

    controllers = {v: ScriptedValve([(0.0, 1.0)]) for v in VALVES}
    records = run_simulation(FMU, controllers, exogenous, duration=6 * 3600.0,
                             control_dt=60.0, output_names=OUTPUTS, record_dt=300.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / "mt_scenario_a_balancing.csv", index=False)

    final = df.iloc[-1]
    flows = [final[m] * 1000 for m in MFLOWS]
    n_flo = N_APT // 2  # nApeFlo = 2 in the default build

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [f"apt {i+1}\n(floor {i//2 + 1})" for i in range(N_APT)]
    bars = ax.bar(labels, flows)
    for bar, fl in zip(bars, flows):
        ax.annotate(f"{fl:.1f}", (bar.get_x() + bar.get_width()/2, fl),
                    ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("mass flow / g/s")
    ax.set_title("All valves open: riser losses starve the upper floors")
    fig.tight_layout()
    fig.savefig(RESULTS / "mt_scenario_a_balancing.png", dpi=150)

    ground = sum(flows[:2]) / 2
    top = sum(flows[-2:]) / 2
    print(f"  mean flow ground floor: {ground:.1f} g/s, top floor: {top:.1f} g/s "
          f"({(top/ground - 1)*100:+.1f} %)")


def scenario_b():
    print("Scenario B: winter week, PI per apartment, apartment 3 vacant ...")

    def exogenous(t):
        t_out = winter_weather(t)
        return {"TOut": t_out, "TSupSet": heating_curve(t_out)}

    schedules = SCHEDULES
    controllers = {}
    for i in range(1, N_APT + 1):
        sched = schedules.get(i)
        if sched is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        else:
            controllers[f"yVal[{i}]"] = PIThermostat(
                f"TRoom[{i}]", day_night_setpoint(*sched))

    records = run_simulation(FMU, controllers, exogenous, duration=7 * DAY,
                             control_dt=60.0, output_names=OUTPUTS, record_dt=300.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / "mt_scenario_b_week.csv", index=False)

    days = df["time"] / DAY
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    ax = axes[0]
    for i in range(1, N_APT + 1):
        style = dict(lw=2.2, color="black") if schedules.get(i) is None else dict(lw=1.0)
        label = f"apt {i} (vacant)" if schedules.get(i) is None else f"apt {i}"
        ax.plot(days, df[f"TRoom[{i}]"] - C2K, label=label, **style)
    ax.plot(days, df["TOut"] - C2K, color="gray", lw=0.8, label="outdoor")
    ax.set_ylabel("temperature / °C")
    ax.legend(loc="center right", fontsize=8, ncols=2)
    ax.set_title("Winter week, 6 apartments — apartment 3 vacant (heat theft)")

    ax = axes[1]
    for i in range(1, N_APT + 1):
        ax.plot(days, df[f"yVal[{i}]"], lw=0.9, label=f"apt {i}")
    ax.set_ylabel("valve position / –")
    ax.legend(loc="center right", fontsize=8, ncols=2)

    ax = axes[2]
    ax.plot(days, df["QBoi"] / 1000, label="boiler power / kW")
    ax.plot(days, df["TSup"] - C2K, lw=0.8, label="supply °C")
    ax.plot(days, df["TRet"] - C2K, lw=0.8, label="return °C")
    ax.set_ylabel("plant")
    ax.set_xlabel("time / days")
    ax.legend(loc="center right", fontsize=8)

    fig.tight_layout()
    fig.savefig(RESULTS / "mt_scenario_b_week.png", dpi=150)

    d2 = df[df["time"] > DAY]
    print(f"  vacant apartment mean temperature: "
          f"{(d2['TRoom[3]'] - C2K).mean():.1f} degC (unheated, held up by neighbours)")
    for i in (1, 4):
        print(f"  apt {i} mean temperature (days 2-7): "
              f"{(d2[f'TRoom[{i}]'] - C2K).mean():.1f} degC")
    print(f"  boiler energy: {d2['QBoi'].mean() * 6 * 24 / 1000:.1f} kWh over days 2-7")
    print(f"  pump energy:   {d2['PPum'].mean() * 6 * 24 / 1000:.2f} kWh over days 2-7")


if __name__ == "__main__":
    scenario_a()
    scenario_b()
    print("done — plots and CSVs in results/")
