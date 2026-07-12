"""Oscillation-signature verification of the 80s building.

Full realism stack: cycling two-point boiler (Python relay), realistic
eTRVs (sampled control, sensor bias, backlash, adaptation), riser water
columns, stochastic internal gains and window events, clear-sky solar,
balanced presets if available. Real building measurements show sustained
oscillations in supply/room temperatures and radiator flows; this run
checks that the simulator now reproduces those signatures.

Run inside the container:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_oscillation_check.py
"""

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from harness import run_simulation
from thermostat import ElectronicThermostat, SampledPI
from boiler import TwoPointBoiler
from gains import InternalGains
from solar import SolarGainModel
from runstore import create_run
from scenario_common import C2K, DAY
from run_balancing import (FMU, N_ZON, N_FLO, T_SET, q_rad_nominal,
                           heating_curve_9070, manual_inputs, zone_k)
import kpi

RESULTS = Path(__file__).resolve().parents[1] / "results"
ORIENT = {1: 180.0, 2: 180.0, 3: 0.0, 4: 0.0, 5: 180.0, 6: 180.0, 7: 0.0, 8: 0.0}
WIN_AREA = {1: 4.6, 2: 2.8, 3: 1.8, 4: 0.8, 5: 4.6, 6: 2.8, 7: 1.8, 8: 0.8}
ROOM_SHORT = ["living", "bed", "kitchen", "bath"]

DUR = 2 * DAY


def weather(t):
    return C2K - 5.0 + 3.0 * math.sin(2 * math.pi * (t - 10 * 3600) / DAY)


def build():
    presets_file = RESULTS / "presets_80s.json"
    presets = json.loads(presets_file.read_text()) if presets_file.exists() else None
    manuals = manual_inputs(presets)

    sol = SolarGainModel(ORIENT, days=3, cloudiness=0.3,
                         window_area_m2=WIN_AREA, g_value=0.75)
    intern = InternalGains(N_ZON, days=3, seed=7)

    def exogenous(t):
        solar = sol.gains(t)
        internal = intern.gains(t)
        return {"TOut": weather(t),
                **{f"QGain[{k}]": solar[f"QGain[{(k - 1) % 8 + 1}]"] + internal[k]
                   for k in range(1, N_ZON + 1)},
                **manuals}

    controllers = {"TSupSet": TwoPointBoiler(
        lambda t: heating_curve_9070(weather(t)))}
    for f in range(1, N_FLO + 1):
        for s in range(8):
            k = zone_k(f, s)
            controllers[f"yVal[{k}]"] = ElectronicThermostat(
                temp_output=f"TRoom[{k}]",
                q_rad_output=f"QRad[{k}]",
                dp_output=f"dpVal[{k}]",
                algorithm=SampledPI(T_SET[s] + C2K),
                q_rad_nominal=q_rad_nominal(f, s),
                seed=k)
    return controllers, exogenous, presets


def check(label, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def main():
    controllers, exogenous, presets = build()
    outputs = ([f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
               + [f"mFlow[{k}]" for k in range(1, N_ZON + 1)]
               + [f"QRad[{k}]" for k in range(1, N_ZON + 1)]
               + [f"dpVal[{k}]" for k in range(1, N_ZON + 1)]
               + ["TSup", "TRet", "QBoi", "PPum"])

    writer = create_run("typical-day-80s-realistic", {
        "durationDays": DUR / DAY,
        "building": {"floors": N_FLO, "apartmentsPerFloor": 8,
                     "model": "Building80s"},
        "scenario": {"weather": "typical winter, cycling boiler, eTRVs, "
                                "stochastic gains",
                     "startDate": "2026-01-12",
                     "balanced": presets is not None},
        "apartments": [{"id": k, "floor": (k - 1) // 8 + 1,
                        "facade": "south" if (k - 1) % 8 in (0, 1, 4, 5) else "north",
                        "vacant": False, "controller": "eTRV / SampledPI",
                        "room": f"{ROOM_SHORT[(k - 1) % 4]} "
                                f"A{1 if (k - 1) % 8 < 4 else 2}",
                        "schedule": f"{T_SET[(k - 1) % 8]:g} °C const"}
                       for k in range(1, N_ZON + 1)],
    })
    # 30 s communication step: bounds the internal solver's step across the
    # discontinuous input changes (relay switching, sampled eTRV moves)
    records = run_simulation(FMU, controllers, exogenous, duration=DUR,
                             control_dt=30.0, output_names=outputs,
                             record_dt=60.0, on_record=writer.append)
    df = pd.DataFrame(records)
    writer.finish(kpis={"boilerKwh": round(kpi.boiler_energy_kwh(df), 1),
                        "pumpKwh": round(kpi.pump_energy_kwh(df), 2)})

    d = df[df["time"] >= DAY].reset_index(drop=True)

    # oscillation signatures, day 2
    firing = (d["QBoi"] > 500).astype(int)
    starts = int(((firing.diff() == 1)).sum())
    pkpk = d["TSup"].quantile(0.98) - d["TSup"].quantile(0.02)
    troom = d["TRoom[9]"] - C2K
    ripple = (troom - troom.rolling(60, center=True, min_periods=1).mean()).std()
    flow = d["mFlow[9]"] * 3600
    flow_var = flow.std() / max(flow.mean(), 1e-6)

    print(f"\nOscillation signatures (day 2, living room floor 2):")
    ok = True
    ok &= check("burner starts 10-250 per day", 10 <= starts <= 250,
                f"{starts} starts")
    ok &= check("supply sawtooth 5-20 K pk-pk", 5 <= pkpk <= 20,
                f"{pkpk:.1f} K")
    ok &= check("room ripple 0.02-0.6 K (std, detrended)",
                0.02 <= ripple <= 0.6, f"{ripple:.3f} K")
    ok &= check("flow fluctuation CV > 0.1", flow_var > 0.1,
                f"{flow_var:.2f}")

    # 6-hour zoom plot, day 2 morning
    z = df[(df["time"] >= DAY + 6 * 3600) & (df["time"] <= DAY + 12 * 3600)]
    hours = (z["time"] - DAY) / 3600
    fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    axes[0].plot(hours, z["TSup"] - C2K, label="supply")
    axes[0].plot(hours, z["TRet"] - C2K, label="return")
    axes[0].set_ylabel("water / °C")
    axes[0].legend(fontsize=8)
    axes[0].set_title("Cycling boiler, eTRVs, riser lag, stochastic gains — day 2, 06-12 h")
    axes[1].plot(hours, z["TRoom[9]"] - C2K, label="living A1 floor 2")
    axes[1].plot(hours, z["TRoom[11]"] - C2K, label="kitchen A1 floor 2")
    axes[1].set_ylabel("room / °C")
    axes[1].legend(fontsize=8)
    axes[2].plot(hours, z["mFlow[9]"] * 3600, label="living A1 floor 2")
    axes[2].set_ylabel("flow / l/h")
    axes[2].legend(fontsize=8)
    axes[3].plot(hours, z["QBoi"] / 1000)
    axes[3].set_ylabel("burner / kW")
    axes[3].set_xlabel("time / h")
    fig.tight_layout()
    fig.savefig(RESULTS / "oscillation_check_80s.png", dpi=150)

    print(f"\noscillation check {'PASSED' if ok else 'FAILED'} — "
          f"plot in results/oscillation_check_80s.png")


if __name__ == "__main__":
    main()
