"""Radiator steady-state operating points vs analytical models.

Virtual test rig: one radiator (living A1, floor 2) is swept through a
staircase of TRV openings while all other radiators stay closed; each
2-hour hold yields a steady (m_flow, TRoom, QRad, TSup) sample from the
FMU. Each sample is compared at identical boundary conditions against:

  exact  — continuous solution of m cp dT/dx = -UA (T - T_room)^n,
           UA calibrated to the 90/70/20 rating point (N = 400 elements)
  LMTD   — the engineering-standard logarithmic mean overtemperature
           formula Q = Q_nom (dTheta_log / dTheta_log_nom)^n
  5-elem — Python replica of the Buildings RadiatorEN442_2 discretization

Approximations documented: radiator inlet temperature is corrected for the
riser shaft loss (G = 6 W/K to 15 degC); the radiant fraction (0.35) sees
the zone mass node, approximated here by the measured air temperature
(quasi-steady difference < 0.5 K).

Run inside the container (needs build/Building80s.fmu):
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_radiator_check.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from harness import run_simulation
from controllers import ScriptedValve
from scenario_common import C2K
from run_balancing import (FMU, N_ZON, q_rad_nominal, manual_inputs, zone_k)

RESULTS = Path(__file__).resolve().parents[1] / "results"

K_TEST = 9            # living A1, floor 2
Q_NOM = q_rad_nominal(2, 0)
T_A_NOM, T_B_NOM, T_AIR_NOM = 90.0, 70.0, 20.0
N_EXP = 1.24
CP = 4186.0
M_NOM = Q_NOM / CP / (T_A_NOM - T_B_NOM)
G_RISER = 6.0         # W/K, stack shaft loss upstream of the radiator
T_SHAFT = 15.0

STAIR = [1.0, 0.6, 0.45, 0.35, 0.28, 0.22, 0.18, 0.14, 0.10]
HOLD = 2 * 3600.0


def discrete_radiator(m, t_in, t_room, n_ele):
    """Element-wise EN 442 solution (the Buildings formulation).
    UA per element calibrated so the rating point is met exactly."""
    def q_total(ua_ele, m_, t_in_, t_room_):
        t = t_in_
        q = 0.0
        for _ in range(n_ele):
            # element energy balance: m cp (t - t_out) = ua_ele*(t_mid-room)^n
            # solved by fixed point on the element outlet
            t_out = t
            for _ in range(60):
                t_mid = t_out  # Buildings uses the element state (outlet)
                dq = ua_ele * np.sign(t_mid - t_room_) * \
                    abs(t_mid - t_room_) ** N_EXP
                t_new = t - dq / (m_ * CP)
                if abs(t_new - t_out) < 1e-9:
                    break
                t_out = 0.5 * t_out + 0.5 * t_new
            q += ua_ele * np.sign(t_out - t_room_) * \
                abs(t_out - t_room_) ** N_EXP
            t = t_out
        return q

    # calibrate ua_ele at rating
    lo, hi = 1e-3, 1e3
    for _ in range(80):
        mid = np.sqrt(lo * hi)
        if q_total(mid, M_NOM, T_A_NOM, T_AIR_NOM) < Q_NOM:
            lo = mid
        else:
            hi = mid
    ua_ele = np.sqrt(lo * hi)
    return q_total(ua_ele, m, t_in, t_room)


def lmtd_radiator(m, t_in, t_room):
    """Q = Q_nom (dTheta_log/dTheta_log_nom)^n with Q = m cp (t_in - t_ret)."""
    dt_log_nom = (T_A_NOM - T_B_NOM) / np.log((T_A_NOM - T_AIR_NOM)
                                              / (T_B_NOM - T_AIR_NOM))
    lo, hi = t_room + 1e-3, t_in - 1e-6
    for _ in range(200):
        t_ret = 0.5 * (lo + hi)
        if t_in - t_ret < 1e-9 or t_ret - t_room < 1e-9:
            break
        dt_log = (t_in - t_ret) / np.log((t_in - t_room) / (t_ret - t_room))
        q_char = Q_NOM * (dt_log / dt_log_nom) ** N_EXP
        q_flow = m * CP * (t_in - t_ret)
        if q_flow > q_char:
            lo = t_ret
        else:
            hi = t_ret
    return m * CP * (t_in - 0.5 * (lo + hi))


def measure_staircase():
    controllers = {f"yVal[{k}]": ScriptedValve([(0.0, 0.0)])
                   for k in range(1, N_ZON + 1)}
    controllers[f"yVal[{K_TEST}]"] = ScriptedValve(
        [(i * HOLD, y) for i, y in enumerate(STAIR)])
    manuals = manual_inputs(None)

    def exogenous(t):
        return {"TOut": C2K - 5.0, "TSupSet": C2K + 75.0,
                **{f"QGain[{k}]": 0.0 for k in range(1, N_ZON + 1)},
                **manuals}

    outputs = [f"mFlow[{K_TEST}]", f"QRad[{K_TEST}]", f"TRoom[{K_TEST}]",
               "TSup"]
    records = run_simulation(FMU, controllers, exogenous,
                             duration=len(STAIR) * HOLD, control_dt=60.0,
                             output_names=outputs, record_dt=60.0)
    df = pd.DataFrame(records)
    samples = []
    for i, y in enumerate(STAIR):
        window = df[(df["time"] >= (i + 1) * HOLD - 900)
                    & (df["time"] < (i + 1) * HOLD)].mean()
        samples.append({
            "y": y,
            "m": window[f"mFlow[{K_TEST}]"],
            "q_fmu": window[f"QRad[{K_TEST}]"],
            "t_room": window[f"TRoom[{K_TEST}]"] - C2K,
            "t_sup": window["TSup"] - C2K,
        })
    return samples


def main():
    print(f"Radiator rig: living A1 floor 2, Q_nom = {Q_NOM:.0f} W at "
          f"90/70/20, m_nom = {M_NOM*1000:.1f} g/s")
    samples = measure_staircase()

    rows = []
    for s in samples:
        if s["m"] < 1e-5:
            continue
        # riser shaft loss between plant sensor and radiator inlet
        t_in = s["t_sup"] - G_RISER * (s["t_sup"] - T_SHAFT) / (s["m"] * CP)
        q_exact = discrete_radiator(s["m"], t_in, s["t_room"], n_ele=400)
        q_lmtd = lmtd_radiator(s["m"], t_in, s["t_room"])
        q_5 = discrete_radiator(s["m"], t_in, s["t_room"], n_ele=5)
        rows.append({**s, "t_in": t_in, "q_exact": q_exact,
                     "q_lmtd": q_lmtd, "q_5elem": q_5})
        print(f"  y={s['y']:.2f} m={s['m']*1000:6.1f} g/s "
              f"Troom={s['t_room']:5.1f} °C | FMU {s['q_fmu']:6.0f} W | "
              f"5elem {q_5:6.0f} | exact {q_exact:6.0f} | LMTD {q_lmtd:6.0f}"
              f" | FMU/exact {s['q_fmu']/q_exact*100:5.1f} % "
              f"| LMTD/exact {q_lmtd/q_exact*100:5.1f} %")

    df = pd.DataFrame(rows)
    dev_fmu = (df["q_fmu"] / df["q_exact"] - 1).abs().max() * 100
    dev_5 = (df["q_fmu"] / df["q_5elem"] - 1).abs().max() * 100
    dev_lmtd = (df["q_lmtd"] / df["q_exact"] - 1).abs().max() * 100
    print(f"\n  max |FMU - exact|:   {dev_fmu:.1f} %")
    print(f"  max |FMU - 5elem|:   {dev_5:.1f} %  (validates extraction)")
    print(f"  max |LMTD - exact|:  {dev_lmtd:.1f} %  (standard formula error)")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    mf = df["m"] / M_NOM
    ax1.plot(mf, df["q_exact"], "-", label="exact (N=400)")
    ax1.plot(mf, df["q_5elem"], "--", label="5 elements (Buildings)")
    ax1.plot(mf, df["q_lmtd"], ":", label="LMTD formula")
    ax1.plot(mf, df["q_fmu"], "o", ms=5, mfc="none", label="FMU measured")
    ax1.set_xlabel("flow / design flow")
    ax1.set_ylabel("heat output / W")
    ax1.set_title("Radiator operating points vs analytical models")
    ax1.legend(fontsize=8)

    ax2.plot(mf, (df["q_fmu"] / df["q_exact"] - 1) * 100, "o-",
             label="FMU vs exact")
    ax2.plot(mf, (df["q_lmtd"] / df["q_exact"] - 1) * 100, "s--",
             label="LMTD vs exact")
    ax2.axhline(0, color="gray", lw=0.7)
    ax2.set_xlabel("flow / design flow")
    ax2.set_ylabel("deviation / %")
    ax2.set_title("Model deviations across the throttling range")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / "radiator_check_80s.png", dpi=150)
    print("\nplot in results/radiator_check_80s.png")


if __name__ == "__main__":
    main()
