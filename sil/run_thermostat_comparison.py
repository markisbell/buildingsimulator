"""Ideal PI vs realistic eTRV — same building, weather and schedules.

Quantifies what thermostat hardware constraints cost: the realistic device
samples every 5 min, senses a radiator-biased quantized noisy temperature,
and only moves the valve when it is worth the battery.

Run inside the container:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_thermostat_comparison.py
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
from thermostat import ElectronicThermostat, SampledPI
from scenario_common import (C2K, DAY, SCHEDULES, day_night_setpoint,
                             default_orientations, make_winter_scenario)
from runstore import create_run
import kpi

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

md = read_model_description(FMU)
N_APT = len([v for v in md.modelVariables if re.fullmatch(r"TRoom\[\d+\]", v.name)])
OUTPUTS = ([f"TRoom[{i}]" for i in range(1, N_APT + 1)]
           + [f"mFlow[{i}]" for i in range(1, N_APT + 1)]
           + [f"QRad[{i}]" for i in range(1, N_APT + 1)]
           + [f"dpVal[{i}]" for i in range(1, N_APT + 1)]
           + ["TSup", "TRet", "QBoi", "PPum"])

DURATION = 7 * DAY
CONTROL_DT = 60.0

# same weather + solar gains for both runs (south/north facade split)
EXOGENOUS, SOLAR = make_winter_scenario(N_APT)


def build_ideal():
    controllers = {}
    for i in range(1, N_APT + 1):
        sched = SCHEDULES.get(i)
        if sched is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        else:
            controllers[f"yVal[{i}]"] = PIThermostat(
                f"TRoom[{i}]", day_night_setpoint(*sched), dt=CONTROL_DT)
    return controllers


def build_realistic():
    controllers = {}
    for i in range(1, N_APT + 1):
        sched = SCHEDULES.get(i)
        if sched is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        else:
            controllers[f"yVal[{i}]"] = ElectronicThermostat(
                temp_output=f"TRoom[{i}]",
                q_rad_output=f"QRad[{i}]",
                dp_output=f"dpVal[{i}]",
                algorithm=SampledPI(day_night_setpoint(*sched)),
                seed=i)
    return controllers


def ideal_travel(df):
    """Valve travel the ideal controller would demand of the motors."""
    travel, moves = 0.0, 0
    for i in range(1, N_APT + 1):
        if SCHEDULES.get(i) is None:
            continue
        dy = df[f"yVal[{i}]"].diff().abs().dropna()
        travel += dy.sum()
        moves += int((dy > 1e-9).sum())
    return travel, moves


def occupied_discomfort(df, schedules):
    total = 0.0
    for i, sched in schedules.items():
        if sched is None:
            continue
        total += kpi.discomfort_kh(df, f"TRoom[{i}]", day_night_setpoint(*sched))
    return total


def occupied_overheating(df, schedules):
    total = 0.0
    for i, sched in schedules.items():
        if sched is None:
            continue
        total += kpi.overheat_kh(df, f"TRoom[{i}]", day_night_setpoint(*sched))
    return total


def apartments_meta(controller_label):
    ori = default_orientations(N_APT)
    apts = []
    for i in range(1, N_APT + 1):
        sched = SCHEDULES.get(i)
        apts.append({
            "id": i,
            "floor": (i - 1) // 2 + 1,
            "facade": "south" if ori[i] == 180.0 else "north",
            "vacant": sched is None,
            "controller": "—" if sched is None else controller_label,
            "schedule": "vacant" if sched is None else
                        f"{sched[0]:g} °C {sched[2]}–{sched[3]} h / {sched[1]:g} °C",
        })
    return apts


def run(name, controllers, controller_label):
    print(f"running: {name} ...")
    writer = create_run(name, {
        "durationDays": DURATION / DAY,
        "building": {"floors": N_APT // 2, "apartmentsPerFloor": 2},
        "scenario": {"weather": "synthetic winter + clear-sky solar",
                     "cloudiness": 0.4, "startDate": "2026-01-12"},
        "apartments": apartments_meta(controller_label),
    })
    records = run_simulation(FMU, controllers, EXOGENOUS,
                             duration=DURATION, control_dt=CONTROL_DT,
                             output_names=OUTPUTS, record_dt=CONTROL_DT,
                             on_record=writer.append)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / f"cmp_{name}.csv", index=False)

    kpis = {
        "discomfortKh": round(occupied_discomfort(df, SCHEDULES), 1),
        "overheatKh": round(occupied_overheating(df, SCHEDULES), 1),
        "boilerKwh": round(kpi.boiler_energy_kwh(df), 1),
        "pumpKwh": round(kpi.pump_energy_kwh(df), 2),
    }
    thermostats = {n: c for n, c in controllers.items()
                   if isinstance(c, ElectronicThermostat)}
    devices = None
    if thermostats:
        travel, moves = kpi.battery_kpis(thermostats.values())
        kpis["valveTravelStrokes"] = round(travel, 1)
        kpis["valveMoves"] = moves
        devices = {}
        for n, th in thermostats.items():
            i = int(re.search(r"\[(\d+)\]", n).group(1))
            a = th.adaptation or {}
            devices[str(i)] = {
                "zeroErrorUm": round(a.get("zero_error_mm", 0) * 1000),
                "sealEstUm": round((a.get("seal_est_mm") or 0) * 1000),
                "travelMm": round(th.travel_mm, 1),
                "moves": th.n_moves,
                "adaptationAgeDays": round((DURATION - a.get("t", 0)) / DAY, 1),
            }
    else:
        travel, moves = ideal_travel(df)
        kpis["valveTravelStrokes"] = round(travel, 1)
        kpis["valveMoves"] = moves
    writer.finish(kpis=kpis, devices=devices)
    return df


def main():
    ideal_ctrl = build_ideal()
    df_ideal = run("ideal", ideal_ctrl, "ideal PI")

    real_ctrl = build_realistic()
    df_real = run("realistic", real_ctrl, "eTRV / SampledPI")

    # ---------- KPIs ----------
    thermostats = [c for c in real_ctrl.values()
                   if isinstance(c, ElectronicThermostat)]
    travel_r, moves_r = kpi.battery_kpis(thermostats)
    travel_i, moves_i = ideal_travel(df_ideal)

    rows = [
        ("discomfort (K*h, days 2-7, all apts)",
         occupied_discomfort(df_ideal, SCHEDULES),
         occupied_discomfort(df_real, SCHEDULES)),
        ("overheating (K*h > setpoint+1K, days 2-7)",
         occupied_overheating(df_ideal, SCHEDULES),
         occupied_overheating(df_real, SCHEDULES)),
        ("boiler energy (kWh, days 2-7)",
         kpi.boiler_energy_kwh(df_ideal), kpi.boiler_energy_kwh(df_real)),
        ("pump energy (kWh, days 2-7)",
         kpi.pump_energy_kwh(df_ideal), kpi.pump_energy_kwh(df_real)),
        ("valve travel (full strokes, week)", travel_i, travel_r),
        ("valve moves (count, week)", moves_i, moves_r),
    ]
    print(f"\n{'KPI':45s} {'ideal PI':>12s} {'real eTRV':>12s}")
    for label, vi, vr in rows:
        print(f"{label:45s} {vi:12.1f} {vr:12.1f}")

    errs = [abs(th.adaptation["zero_error_mm"]) for th in thermostats
            if th.adaptation is not None]
    if errs:
        print(f"\nadaptation runs: {len(errs)} devices, "
              f"zero-estimate error {min(errs):.3f}-{max(errs):.3f} mm "
              f"(mean {sum(errs)/len(errs):.3f} mm)")

    # ---------- plots ----------
    sched1 = day_night_setpoint(*SCHEDULES[1])
    win = (df_ideal["time"] >= 2 * DAY) & (df_ideal["time"] <= 4 * DAY)
    days_i = df_ideal["time"][win] / DAY
    days_r = df_real["time"][win] / DAY

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    ax = axes[0]
    ax.plot(days_i, df_ideal["TRoom[1]"][win] - C2K, label="ideal PI")
    ax.plot(days_r, df_real["TRoom[1]"][win] - C2K, label="realistic eTRV")
    ax.plot(days_i, [sched1(t) - C2K for t in df_ideal["time"][win]],
            ls="--", lw=0.8, color="gray", label="setpoint")
    ax.set_ylabel("room temperature / °C")
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Apartment 1, days 2-4: what thermostat hardware constraints cost")

    ax = axes[1]
    ax.plot(days_i, df_ideal["yVal[1]"][win], lw=0.8, label="ideal PI (continuous)")
    ax.plot(days_r, df_real["yVal[1]"][win], lw=1.2, label="realistic eTRV (stepped)")
    ax.set_ylabel("valve position / –")
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[2]
    th1 = real_ctrl["yVal[1]"]
    log = pd.DataFrame(th1.sensor_log, columns=["time", "T_true", "T_sensed"])
    lwin = (log["time"] >= 2 * DAY) & (log["time"] <= 4 * DAY)
    ax.plot(log["time"][lwin] / DAY, log["T_true"][lwin] - C2K, label="true room temp")
    ax.plot(log["time"][lwin] / DAY, log["T_sensed"][lwin] - C2K, lw=0.8,
            label="sensor reading (valve-mounted)")
    ax.set_ylabel("temperature / °C")
    ax.set_xlabel("time / days")
    ax.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    fig.savefig(RESULTS / "cmp_ideal_vs_realistic.png", dpi=150)
    print("\ndone — plots and CSVs in results/")


if __name__ == "__main__":
    main()
