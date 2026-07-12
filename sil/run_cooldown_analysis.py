"""Analyze the evening cooldown (setback 22:00) - rates, phases, and the
device-bias floor. Uses both comparison runs: ideal PI vs realistic eTRV.
Evidence figure for docs/heatup-dynamics.md section 5.

Run inside the container after run_thermostat_comparison.py:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_cooldown_analysis.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

C2K = 273.15
DAY = 86400.0
ROOT = Path(__file__).resolve().parents[1]

ideal = pd.read_csv(ROOT / "results" / "cmp_ideal.csv")
real = pd.read_csv(ROOT / "results" / "cmp_realistic.csv")


def window(df, d0=2):
    z = df[(df["time"] >= d0 * DAY + 21.5 * 3600)
           & (df["time"] <= (d0 + 1) * DAY + 6.2 * 3600)].copy()
    z["h"] = (z["time"] - d0 * DAY) / 3600
    return z

zi, zr = window(ideal), window(real)

# cooling rates in the realistic run (apt 1, setback 22:00, night sp 17)
t = zr["h"].to_numpy()
T = (zr["TRoom[1]"] - C2K).to_numpy()


def rate(h0, h1):
    m = (t >= h0) & (t <= h1)
    return np.polyfit(t[m], T[m], 1)[0]

print("cooldown rates, realistic run, apt 1 (setback at 22:00):")
print(f"  22:00-23:00 : {rate(22, 23):+.2f} K/h   (air-node fast phase)")
print(f"  23:00-01:00 : {rate(23, 25):+.2f} K/h   (transition)")
print(f"  01:00-05:00 : {rate(25, 29):+.2f} K/h   (slow/mass phase or floor)")
q = zr["QRad[1]"].to_numpy()
first_reheat = t[(t > 22) & (q > 100)]
print(f"  radiator re-engages at: {first_reheat[0]:.2f} h"
      if len(first_reheat) else "  radiator stays off")

fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
axes[0].plot(zi["h"], zi["TRoom[1]"] - C2K, label="ideal PI (true air temp)")
axes[0].plot(zr["h"], zr["TRoom[1]"] - C2K, label="realistic eTRV (true air temp)")
axes[0].axhline(17, color="gray", ls="--", lw=0.8)
axes[0].text(30.1, 17.05, "night setpoint 17 °C", fontsize=8, color="gray")
axes[0].axvline(22, color="gray", ls=":", lw=0.8)
axes[0].set_ylabel("room 1 / °C")
axes[0].legend(fontsize=9)
axes[0].set_title("Evening cooldown, day 2 → 3 (setback 22:00)")
axes[1].plot(zi["h"], zi["QRad[1]"], label="ideal PI")
axes[1].plot(zr["h"], zr["QRad[1]"], label="realistic eTRV")
axes[1].set_ylabel("radiator power / W")
axes[1].set_xlabel("hour (day 2 continued)")
axes[1].legend(fontsize=9)
fig.tight_layout()
fig.savefig(ROOT / "results" / "cooldown_analysis.png", dpi=150)
print("wrote results/cooldown_analysis.png")
