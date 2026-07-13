"""Neighbor-coupling cooldown experiment (Building80s, field protocol).

Field cooldown measurements are usually taken in an occupied building: one
room is set back while the neighbors stay warm and feed it through party
walls, slabs and the hall. Our verification scenarios set back the whole
building synchronously, which kills exactly those couplings. This script
quantifies the difference:

  Case SYNC   : all 24 rooms set back by 3 K at t0 = 48 h.
  Case SINGLE : only the test room (living S, apartment 1, mid floor,
                zone 9) is set back; every other room holds its setpoint.

Both runs are otherwise identical: constant -5 degC, no solar, no internal
gains, ideal PI per room, manuals open, outdoor-reset supply.

  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_neighbor_test.py
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fmpy import read_model_description

from controllers import PIThermostat
from harness import run_simulation

C2K = 273.15
H = 3600.0
ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "Building80s.fmu")
RESULTS = ROOT / "results"

SETPOINTS = [20.0, 20.0, 20.0, 24.0] * 2  # per stack, bath 24
TEST_ZONE = 9        # (floor 2 - 1)*8 + stack 1 = living S, apt 1, mid floor
NEIGHBORS = {1: "living below (floor 1)", 17: "living above (floor 3)",
             10: "bedroom next door"}
SETBACK = 3.0        # K
T0 = 48 * H          # setback instant (after 2 warm-up days)
T_END = 60 * H       # 12 h setback window
T_OUT = -5.0 + C2K

md = read_model_description(FMU)
N_ZON = len([v for v in md.modelVariables
             if re.fullmatch(r"TRoom\[\d+\]", v.name)])
OUTPUTS = ([f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
           + [f"QRad[{TEST_ZONE}]", "TSup", "TRet"])
MANUALS = {**{f"yPreset[{k}]": 1.0 for k in range(1, N_ZON + 1)},
           **{f"yBalance[{s}]": 1.0 for s in range(1, 9)}}


def t_sup_set(_t):
    # 90/70 outdoor-reset curve at -5 degC
    return 30.0 + 60.0 * (20.0 - (-5.0)) / 32.0 + C2K


def scenario(t):
    exo = {"TOut": T_OUT, "TSupSet": t_sup_set(t)}
    exo.update({f"QGain[{k}]": 0.0 for k in range(1, N_ZON + 1)})
    exo.update(MANUALS)  # rings and riser valves open — without these the
    return exo           # network is shut and the building free-cools


def make_controllers(setback_zones):
    ctrl = {}
    for k in range(1, N_ZON + 1):
        sp_day = SETPOINTS[(k - 1) % 8] + C2K

        def sp(t, sp_day=sp_day, back=(k in setback_zones)):
            return sp_day - (SETBACK if back and t >= T0 else 0.0)

        ctrl[f"yVal[{k}]"] = PIThermostat(f"TRoom[{k}]", sp, kp=0.3, ti=1800.0)
    return ctrl


def run(name, setback_zones):
    print(f"running: {name} ...", flush=True)
    records = run_simulation(FMU, make_controllers(setback_zones), scenario,
                             duration=T_END, control_dt=30.0,
                             output_names=OUTPUTS, record_dt=120.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / f"neighbor_test_{name}.csv", index=False)
    return df


def rates(df):
    t = (df["time"].to_numpy() - T0) / H
    T = df[f"TRoom[{TEST_ZONE}]"].to_numpy() - C2K

    def rate(h0, h1):
        m = (t >= h0) & (t <= h1)
        return np.polyfit(t[m], T[m], 1)[0]

    after8 = T[np.searchsorted(t, 8.0)]
    return rate(0, 1), rate(1, 3), rate(3, 8), T[np.searchsorted(t, 0.0)] - after8


sync = run("sync", set(range(1, N_ZON + 1)))
single = run("single", {TEST_ZONE})

print(f"\ncooldown of zone {TEST_ZONE} (living S, apt 1, mid floor), "
      f"setback {SETBACK:g} K at t0, -5 degC outside:")
for name, df in [("synchronized (whole building)", sync),
                 ("single room (neighbors warm)", single)]:
    r1, r23, r48, drop8 = rates(df)
    print(f"  {name:32s}: first hour {r1:+.2f} K/h | h2-3 {r23:+.2f} K/h | "
          f"h4-8 {r48:+.2f} K/h | drop after 8 h {drop8:.2f} K")

# ---- figure ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
for df, label, color in [(sync, "synchronized setback (whole building)", "#B8432F"),
                         (single, "single-room setback (neighbors warm)", "#2E5E8C")]:
    t = (df["time"] - T0) / H
    m = (t >= -2) & (t <= 12)
    ax1.plot(t[m], df[f"TRoom[{TEST_ZONE}]"][m] - C2K, lw=1.8,
             label=label, color=color)
ax1.axhline(SETPOINTS[0] - SETBACK, color="gray", ls="--", lw=0.8)
ax1.axvline(0, color="gray", ls=":", lw=0.8)
ax1.set_ylabel(f"test room (zone {TEST_ZONE}) / °C")
ax1.set_title("Cooldown of one living room: whole-building vs single-room setback "
              "(-5 °C, no sun/gains, ideal PI)")
ax1.legend(fontsize=9)

t = (single["time"] - T0) / H
m = (t >= -2) & (t <= 12)
for k, label in NEIGHBORS.items():
    ax2.plot(t[m], single[f"TRoom[{k}]"][m] - C2K, lw=1.2, label=label)
ax2.plot(t[m], single[f"TRoom[{TEST_ZONE}]"][m] - C2K, lw=1.8, color="#2E5E8C",
         label="test room")
ax2.set_xlabel("hours after setback")
ax2.set_ylabel("single-room case / °C")
ax2.set_title("Single-room case: the neighbors hold their setpoints and feed the test room")
ax2.legend(fontsize=9)

fig.tight_layout()
fig.savefig(RESULTS / "neighbor_test_80s.png", dpi=150)
print("wrote results/neighbor_test_80s.png")
