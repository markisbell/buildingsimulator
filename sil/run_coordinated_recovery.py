"""Phase 3, strategy 4: distributed considerate recovery (Building80s).

The fairness experiment: as-built presetting-ring scatter (same seeded
pattern as run_balancing.py), whole-building night setback, morning
recovery through the two-point boiler with Schnellaufheizung. Two
identical runs of room-level eTRVs (bias compensation + battery policies):

    greedy       coordination off — every device recovers at full open
    considerate  arrived devices cap at y=0.20 while any peer still
                 reports a deficit > 0.8 K (RecoveryCoordinator channel)

Metrics on the day-3 recovery (06:00): per-room deficit trajectories,
worst deficit at +1/+2/+3 h, spread, and the time until every room is
within 0.5 K of its day setpoint.

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work/sil && /opt/silenv/bin/python3 run_coordinated_recovery.py"
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fmpy import read_model_description

from boiler import Schnellaufheizung, TwoPointBoiler
from harness import run_simulation
from scenario_common import C2K, DAY, day_night_setpoint
from strategies import (BatteryAwareThermostat, ConsiderateRecoveryThermostat,
                        RecoveryCoordinator)
from thermostat import SampledPI

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "Building80s.fmu")
RESULTS = ROOT / "results"

# room tables (docs/building80s-parameters.md sections 3-4)
G_WIN = [26.1, 16.7, 10.6, 5.6] * 2
G_WAL_MID = [15.3, 11.6, 5.0, 3.7] * 2
G_GND = [8.8, 5.9, 3.7, 2.2] * 2
G_TOP = [11.6, 7.7, 4.8, 2.9] * 2
T_SET_DAY = [20.0, 20.0, 20.0, 24.0] * 2
SETBACK = 3.0
DAY_START_H, DAY_END_H = 6, 22
T_OUT = -5.0 + C2K
OVERSIZE = 1.3

md = read_model_description(FMU)
N_ZON = len([v for v in md.modelVariables
             if re.fullmatch(r"TRoom\[\d+\]", v.name)])
N_FLO = N_ZON // 8
OUTPUTS = ([f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
           + [f"QRad[{k}]" for k in range(1, N_ZON + 1)]
           + [f"dpVal[{k}]" for k in range(1, N_ZON + 1)]
           + ["TSup", "TRet", "QBoi"])

# Evaluate the day-6 recovery: the night-anchor bias learning needs ~5
# closures to converge (k_hat ~90 %); at day 3 every room still plateaus
# 1.3-1.6 K short on residual sensor bias and no arrival threshold is
# reachable (first-attempt finding).
DURATION = 6 * DAY + 14 * 3600.0
CONTROL_DT = 30.0
T0 = 5 * DAY + DAY_START_H * 3600.0  # day-6 boost instant


def stack_of(k):
    return (k - 1) % 8


def q_rad_nominal(k):
    f, s = (k - 1) // 8 + 1, stack_of(k)
    g_wal = G_WAL_MID[s] + (G_GND[s] if f == 1 else 0.0) \
        + (G_TOP[s] if f == N_FLO else 0.0)
    return OVERSIZE * ((G_WIN[s] + g_wal) * (T_SET_DAY[s] + 12.0)
                       + 15.0 * (T_SET_DAY[s] - 19.0))


def setpoint_fn(k):
    s = stack_of(k)
    return day_night_setpoint(T_SET_DAY[s], T_SET_DAY[s] - SETBACK,
                              DAY_START_H, DAY_END_H)


def heating_curve(_t):
    # 90/70 outdoor-reset at constant -5 degC
    return 30.0 + 60.0 * (20.0 - (-5.0)) / 32.0 + C2K


AS_BUILT = {f"yPreset[{k}]": float(v) for k, v in zip(
    range(1, N_ZON + 1),
    np.random.default_rng(42).uniform(0.30, 1.0, N_ZON))}
MANUALS = {**AS_BUILT, **{f"yBalance[{s}]": 1.0 for s in range(1, 9)}}


def scenario(t):
    exo = {"TOut": T_OUT}
    exo.update({f"QGain[{k}]": 0.0 for k in range(1, N_ZON + 1)})
    exo.update(MANUALS)
    return exo


def build(considerate):
    coordinator = RecoveryCoordinator() if considerate else None
    controllers = {}
    for k in range(1, N_ZON + 1):
        kwargs = dict(temp_output=f"TRoom[{k}]", q_rad_output=f"QRad[{k}]",
                      dp_output=f"dpVal[{k}]",
                      q_rad_nominal=q_rad_nominal(k),
                      algorithm=SampledPI(setpoint_fn(k)), seed=k)
        if considerate:
            controllers[f"yVal[{k}]"] = ConsiderateRecoveryThermostat(
                coordinator=coordinator, day_start_h=DAY_START_H, **kwargs)
        else:
            controllers[f"yVal[{k}]"] = BatteryAwareThermostat(**kwargs)
    rooms = {f"TRoom[{k}]": setpoint_fn(k) for k in range(1, N_ZON + 1)}
    booster = Schnellaufheizung(heating_curve, rooms, day_start_h=DAY_START_H,
                                boost_dK=12.0, t_sup_max=363.15)
    controllers["TSupSet"] = TwoPointBoiler(heating_curve, booster=booster)
    return controllers


def run(name, considerate):
    print(f"running: {name} ...", flush=True)
    controllers = build(considerate)
    records = run_simulation(FMU, controllers, scenario,
                             duration=DURATION, control_dt=CONTROL_DT,
                             output_names=OUTPUTS, record_dt=120.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / f"coord_{name}.csv", index=False)
    ks = [c.k_hat for c in controllers.values() if hasattr(c, "k_hat")]
    caps = [c.cap_time_s / 3600 for c in controllers.values()
            if hasattr(c, "cap_time_s")]
    print(f"  k_hat: min {min(ks):.2f} / median {sorted(ks)[len(ks)//2]:.2f} "
          f"/ max {max(ks):.2f}")
    if caps and max(caps) > 0:
        print(f"  cap time per device (h): median "
              f"{sorted(caps)[len(caps)//2]:.2f}, max {max(caps):.2f}")
    return df


def deficits(df):
    """Per-room deficit trajectories on the day-3 recovery window."""
    w = df[(df["time"] >= T0 - 1800) & (df["time"] <= T0 + 5 * 3600)]
    h = (w["time"].to_numpy() - T0) / 3600.0
    d = {k: (T_SET_DAY[stack_of(k)] + C2K - w[f"TRoom[{k}]"].to_numpy())
         for k in range(1, N_ZON + 1)}
    return h, d


def metrics(df):
    h, d = deficits(df)
    out = {}
    for hh in (1.0, 2.0, 3.0):
        i = np.searchsorted(h, hh)
        vals = [d[k][i] for k in d]
        out[f"worst@+{hh:g}h"] = max(vals)
        out[f"spread@+{hh:g}h"] = max(vals) - min(vals)
    arrivals = []
    for thr in (0.75, 0.5):
        arr = []
        for k in d:
            idx = np.nonzero((h >= 0) & (d[k] <= thr))[0]
            arr.append(h[idx[0]] if len(idx) else np.inf)
        finite = [a for a in arr if np.isfinite(a)]
        out[f"arrived rooms (<= {thr} K)"] = len(finite)
        out[f"all-arrived @{thr} K (h)"] = max(arr)
        out[f"mean arrival @{thr} K (h)"] = (float(np.mean(finite))
                                             if finite else np.inf)
        if thr == 0.75:
            arrivals = arr
    return out, arrivals


def main():
    df_g = run("greedy", considerate=False)
    df_c = run("considerate", considerate=True)

    m_g, arr_g = metrics(df_g)
    m_c, arr_c = metrics(df_c)
    print(f"\n{'day-6 recovery metric':24s} {'greedy':>10s} {'considerate':>12s}")
    for key in m_g:
        print(f"{key:24s} {m_g[key]:10.2f} {m_c[key]:12.2f}")

    # ---- figure ----
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (df, title) in zip(axes[0],
                               [(df_g, "greedy recovery"),
                                (df_c, "considerate recovery")]):
        h, d = deficits(df)
        for k in d:
            ax.plot(h, d[k], lw=0.7, alpha=0.5, color="#2E5E8C")
        worst = np.max(np.array(list(d.values())), axis=0)
        ax.plot(h, worst, lw=2.0, color="#B8432F", label="worst room")
        ax.axhline(0.5, color="gray", ls="--", lw=0.8)
        ax.axvline(0, color="gray", ls=":", lw=0.8)
        ax.set_title(title)
        ax.set_xlabel("hours after boost")
        ax.set_ylabel("deficit vs day setpoint / K")
        ax.set_ylim(-1, 4)
        ax.legend(fontsize=8)

    ax = axes[1][0]
    ax.plot(sorted(arr_g), range(1, N_ZON + 1), "o-", color="#B8432F",
            label="greedy")
    ax.plot(sorted(arr_c), range(1, N_ZON + 1), "o-", color="#2E5E8C",
            label="considerate")
    ax.set_xlabel("arrival time after boost / h (within 0.75 K)")
    ax.set_ylabel("rooms arrived")
    ax.legend(fontsize=8)
    ax.set_title("Arrival distribution: coordination pulls in the laggards")

    ax = axes[1][1]
    w = (df_c["time"] >= T0 - 1800) & (df_c["time"] <= T0 + 5 * 3600)
    ax.plot((df_c["time"][w] - T0) / 3600, df_c["TSup"][w] - C2K,
            label="considerate", color="#2E5E8C", lw=1.0)
    w = (df_g["time"] >= T0 - 1800) & (df_g["time"] <= T0 + 5 * 3600)
    ax.plot((df_g["time"][w] - T0) / 3600, df_g["TSup"][w] - C2K,
            label="greedy", color="#B8432F", lw=1.0)
    ax.set_xlabel("hours after boost")
    ax.set_ylabel("supply / °C")
    ax.set_title("Supply during recovery (relay + Schnellaufheizung)")
    ax.legend(fontsize=8)

    fig.suptitle("Distributed considerate recovery — as-built rings, day-3 boost",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(RESULTS / "coordinated_recovery.png", dpi=150)
    print("\nwrote results/coordinated_recovery.png")


if __name__ == "__main__":
    main()
