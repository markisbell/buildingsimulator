"""Quasi-static valve sweep — verifies the TRV insert realism.

Panel 1: apartment 1 valve is ramped 0 -> 1 -> 0 over 12 h (others closed);
         the realized flow shows the sealing dead zone, the steep rise and
         the saturation of the table characteristic, distorted by valve
         authority against the network.
Panel 2: the device-side mechanical play (backlash) between motor command
         and pin position — pure Python, the hysteresis a control algorithm
         actually has to fight.

Run inside the container:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev python3 run_valve_sweep.py
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fmpy import read_model_description

from harness import run_simulation
from controllers import ScriptedValve
from actuator import ValveActuator
from scenario_common import C2K

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

md = read_model_description(FMU)
N_APT = len([v for v in md.modelVariables if re.fullmatch(r"TRoom\[\d+\]", v.name)])

# valve table from ApartmentBranch.mo, for reference overlay
Y_CHA = [0, 0.03, 0.06, 0.10, 0.15, 0.22, 0.30, 0.45, 0.65, 1.0]
PHI_CHA = [1.5e-3, 2e-3, 3e-3, 0.12, 0.35, 0.60, 0.78, 0.88, 0.94, 1.0]

RAMP = 6 * 3600.0  # seconds for one ramp direction


class TriangleValve:
    """0 -> 1 over RAMP seconds, then 1 -> 0."""

    def step(self, t, measurements):
        if t <= RAMP:
            return t / RAMP
        return max(0.0, 2.0 - t / RAMP)


def fmu_sweep():
    print("sweeping valve 1 through the FMU ...")
    controllers = {"yVal[1]": TriangleValve()}
    controllers.update({f"yVal[{i}]": ScriptedValve([(0.0, 0.0)])
                        for i in range(2, N_APT + 1)})
    outputs = ["mFlow[1]", "TRoom[1]"]

    def exogenous(t):
        return {"TOut": C2K - 5.0, "TSupSet": C2K + 60.0}

    records = run_simulation(FMU, controllers, exogenous, duration=2 * RAMP,
                             control_dt=60.0, output_names=outputs, record_dt=60.0)
    df = pd.DataFrame(records)
    df.to_csv(RESULTS / "valve_sweep.csv", index=False)
    return df


def device_hysteresis():
    """Drive the actuator with a slow triangle command (perfectly calibrated
    device, so the plot isolates the mechanical play)."""
    act = ValveActuator(backlash_mm=0.10, initial_zero_error_mm=0.0)
    cmd = np.concatenate([np.linspace(0, 1, 200), np.linspace(1, 0, 200)])
    pin = np.array([act.command_opening(c) for c in cmd])
    return cmd, pin


def main():
    df = fmu_sweep()
    up = df[df["time"] <= RAMP]
    down = df[df["time"] > RAMP]
    m_max = df["mFlow[1]"].max()

    cmd, pin = device_hysteresis()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax1.plot(up["yVal[1]"] * 100, up["mFlow[1]"] / m_max * 100, label="opening")
    ax1.plot(down["yVal[1]"] * 100, down["mFlow[1]"] / m_max * 100,
             ls=":", label="closing")
    ax1.plot(np.array(Y_CHA) * 100, np.array(PHI_CHA) * 100,
             lw=0.8, color="gray", marker=".", ms=4,
             label="Kv table (no network)")
    ax1.axvspan(0, 6, alpha=0.12, color="gray")
    ax1.annotate("sealing\ndead zone", xy=(7, 60), ha="left", fontsize=8)
    ax1.axvline(30, lw=0.6, color="gray", ls=":")
    ax1.annotate("xp = 2 K lift\n(RA-N anchor)", xy=(31, 20), fontsize=8)
    ax1.set_xlabel("commanded stroke / % (100 % = 1.5 mm)")
    ax1.set_ylabel("flow, normalized / %")
    ax1.set_title("Realized flow vs stroke (FMU)")
    ax1.legend(fontsize=8)

    ax2.plot(cmd * 100, pin * 100)
    ax2.plot([0, 100], [0, 100], lw=0.8, color="gray", ls="--")
    ax2.set_xlabel("motor command / % stroke")
    ax2.set_ylabel("pin position / % stroke")
    ax2.set_title("Device mechanics: 0.1 mm play -> hysteresis")

    fig.tight_layout()
    fig.savefig(RESULTS / "valve_sweep.png", dpi=150)

    # numbers for the log
    dead = up[up["yVal[1]"] <= 0.06]["mFlow[1]"].max() / m_max * 100
    anchor = up[(up["yVal[1]"] - 0.3).abs() < 0.01]["mFlow[1]"].mean() / m_max * 100
    print(f"  flow at <=6 % stroke:  {dead:.2f} % of max (dead zone)")
    print(f"  flow at 30 % stroke:   {anchor:.1f} % of max (RA-N anchor: ~81 %)")
    # gap between opening and closing branches at mid-command = play width
    mid_up = pin[np.argmin(np.abs(cmd[:200] - 0.5))]
    mid_dn = pin[200 + np.argmin(np.abs(cmd[200:] - 0.5))]
    print(f"  hysteresis width:      {abs(mid_dn - mid_up) * 1.5:.2f} mm "
          f"(branch gap at mid-stroke)")
    print("done — plot in results/valve_sweep.png")


if __name__ == "__main__":
    main()
